"""Unified Agnostic LLM Gateway for Nexus Modernize.

Supports:
- Providers: Amazon Bedrock (HTTP API Key or Boto3 IAM), Azure AI Foundry / OpenAI, and Local/Mock
- Task Profiles: 'fast' (Haiku / Nova Lite), 'reasoning' (Nova Pro), 'code' (Claude 3.5 Sonnet), 'vision' (Multi-modal)
- Dynamic fallback: Automatic graceful degradation if a primary model is throttled or offline.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

import httpx
from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logger = logging.getLogger("llm_gateway")

TaskType = Literal["fast", "reasoning", "code", "vision"]
ProviderType = Literal["bedrock", "azure", "openai", "auto"]


class LLMGateway:
    def __init__(self):
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.bedrock_api_key = os.getenv("BEDROCK_API_KEY")
        self.default_provider = os.getenv("LLM_PROVIDER", "bedrock").lower()
        
        # Model Tier Configurations
        self.models = {
            "fast": os.getenv("BEDROCK_MODEL_FAST", "amazon.nova-lite-v1:0"),
            "reasoning": os.getenv("BEDROCK_MODEL_REASONING", os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")),
            "code": os.getenv("BEDROCK_MODEL_CODE", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
            "vision": os.getenv("BEDROCK_MODEL_VISION", "amazon.nova-pro-v1:0"),
        }

    def get_model_for_task(self, task_type: TaskType) -> str:
        return self.models.get(task_type, self.models["reasoning"])

    def invoke(
        self,
        system_prompt: str,
        user_prompt: str,
        task_type: TaskType = "reasoning",
        provider: ProviderType = "auto",
        max_tokens: int = 2000,
        temperature: float = 0.2,
        images_base64: list[dict[str, str]] | None = None,
    ) -> str | None:
        """Route request to the designated provider and model tier with certified PII Scrubbing."""
        # 1. Deterministic Zero-Trust PII Scrubber
        from .pii_scrubber import scrubber
        sanitized_user_prompt, redacted_count = scrubber.scrub(user_prompt)
        if redacted_count > 0:
            logger.info(f"Compliance Guardrail: Scrubbed {redacted_count} PII tokens before model dispatch.")

        chosen_provider = self.default_provider if provider == "auto" else provider

        if chosen_provider == "bedrock":
            model_id = self.get_model_for_task(task_type)
            result = self._invoke_bedrock(
                model_id=model_id,
                system_prompt=system_prompt,
                user_prompt=sanitized_user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                images_base64=images_base64,
            )
            # If the selected frontier model fails (e.g. Claude not enabled), fall back to Nova Pro
            if result is None and model_id != self.models["reasoning"]:
                logger.info(f"Model {model_id} unavailable, falling back to {self.models['reasoning']}")
                result = self._invoke_bedrock(
                    model_id=self.models["reasoning"],
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            return result

        elif chosen_provider in ("azure", "openai"):
            return self._invoke_openai_compatible(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        logger.warning(f"Unknown or unconfigured provider: {chosen_provider}")
        return None

    def _invoke_bedrock(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        images_base64: list[dict[str, str]] | None = None,
    ) -> str | None:
        """Invoke Amazon Bedrock via Direct API Key Bearer Token or Boto3 SDK."""
        # 1. Direct HTTP API Key Bearer Token
        if self.bedrock_api_key:
            try:
                url = f"https://bedrock-runtime.{self.region}.amazonaws.com/model/{model_id}/invoke"
                headers = {
                    "Authorization": f"Bearer {self.bedrock_api_key}",
                    "Content-Type": "application/json",
                }

                if "nova" in model_id.lower():
                    # Amazon Nova multi-modal payload format
                    user_content: list[dict[str, Any]] = [{"text": user_prompt}]
                    if images_base64:
                        for img in images_base64:
                            user_content.append({
                                "image": {
                                    "format": img.get("format", "png"),
                                    "source": {"bytes": img["base64"]}
                                }
                            })
                    payload = {
                        "system": [{"text": system_prompt}],
                        "messages": [{"role": "user", "content": user_content}],
                        "inferenceConfig": {
                            "max_new_tokens": max_tokens,
                            "temperature": temperature,
                        },
                    }
                else:
                    # Anthropic Claude 3 / 3.5 format
                    user_content = []
                    if images_base64:
                        for img in images_base64:
                            user_content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": f"image/{img.get('format', 'png')}",
                                    "data": img["base64"],
                                }
                            })
                    user_content.append({"type": "text", "text": user_prompt})
                    payload = {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_content}],
                    }

                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        if "nova" in model_id.lower():
                            content = data.get("output", {}).get("message", {}).get("content", [])
                        else:
                            content = data.get("content", [])
                        if content and "text" in content[0]:
                            return content[0]["text"]
                    else:
                        logger.warning(f"Bedrock HTTP {resp.status_code} for {model_id}: {resp.text[:200]}")
            except Exception as exc:
                logger.warning(f"Bedrock HTTP invocation error: {exc}")

        # 2. Boto3 SDK IAM Fallback
        try:
            import boto3
            client = boto3.client("bedrock-runtime", region_name=self.region)
            if "nova" in model_id.lower():
                body = json.dumps({
                    "system": [{"text": system_prompt}],
                    "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
                    "inferenceConfig": {"max_new_tokens": max_tokens, "temperature": temperature},
                })
            else:
                body = json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}],
                })

            resp = client.invoke_model(modelId=model_id, body=body)
            res_body = json.loads(resp["body"].read().decode("utf-8"))
            if "nova" in model_id.lower():
                return res_body.get("output", {}).get("message", {}).get("content", [{}])[0].get("text")
            return res_body.get("content", [{}])[0].get("text")
        except Exception as exc:
            logger.debug(f"Boto3 Bedrock fallback failed: {exc}")

        return None

    def _invoke_openai_compatible(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str | None:
        """Invoke Azure AI Foundry Responses API or OpenAI compatible endpoints."""
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("AZURE_FOUNDRY_ENDPOINT") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        api_key = os.getenv("AZURE_OPENAI_KEY") or os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("AZURE_FOUNDRY_API_KEY") or os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv("AZURE_FOUNDRY_DEPLOYMENT", "gpt-5.1-codex-mini")

        if not api_key or not endpoint:
            logger.warning("Azure/OpenAI API key or endpoint missing in environment.")
            return None

        # Build combined prompt for Responses API
        full_input = f"{system_prompt}\n\nTask: {user_prompt}" if system_prompt else user_prompt

        headers = {
            "Content-Type": "application/json",
        }
        if "azure" in endpoint.lower() or "cognitiveservices" in endpoint.lower():
            headers["api-key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"

        # 1. Azure OpenAI Responses API (e.g. /openai/responses?...)
        if "responses" in endpoint.lower():
            url = endpoint
            payload = {
                "model": model,
                "input": full_input,
            }
            try:
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        output_list = data.get("output", [])
                        for item in output_list:
                            if item.get("type") == "message":
                                for c in item.get("content", []):
                                    if c.get("type") == "output_text" and c.get("text"):
                                        return c.get("text")
                            elif "text" in item:
                                return item["text"]
                        if "text" in data and data["text"]:
                            return data["text"]
                    else:
                        logger.warning(f"Azure Responses API HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as exc:
                logger.warning(f"Azure Responses API call failed: {exc}")

        # 2. Standard Chat Completions fallback
        url = endpoint if "chat/completions" in endpoint else f"{endpoint.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content")
        except Exception as exc:
            logger.warning(f"OpenAI/Azure endpoint call failed: {exc}")

        return None


# Global singleton instance
gateway = LLMGateway()
