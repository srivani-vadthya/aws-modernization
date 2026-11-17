---
name: api-connector
description: "Axios-based API connector with retry, delay, interceptors, and typed request config — the ONLY pattern for HTTP calls in this codebase"
tags: ["api", "http", "fetch", "axios", "$http", "get", "post", "put", "delete", "request", "service", "connector"]
trigger: api_call
---

# API Connector — Golden Pattern

## When to Apply
**ANY** component or service that calls a backend API endpoint. Never write `fetch()` calls directly or use `axios` directly — always use the `apiRequest` function from this module.

## Exact Golden Pattern

```ts
// filepath: src/scripts/apiConnector.ts
import axios from 'axios';
import type { AxiosInstance, AxiosResponse, AxiosError } from 'axios';

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface ApiRequestConfig {
    url: string;
    method: HttpMethod;
    maxRetries?: number;
    delayBetweenRetries?: number;
    data?: unknown;
    params?: Record<string, unknown>;
    headers?: Record<string, string>;
}

// Single pre-configured Axios instance for the entire app
const axiosInstance: AxiosInstance = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:3007',
    timeout: 30000,
    headers: { 'Content-Type': 'application/json' },
});

const handleResponseError = (error: unknown): Promise<never> => {
    if (axios.isAxiosError(error)) {
        const axiosError = error as AxiosError;
        const status = axiosError.response?.status;
        const errorMessages: Record<number, string> = {
            401: 'Unauthorized - redirecting to login',
            400: 'Bad request',
            500: 'Server error',
        };
        if (status && errorMessages[status]) console.error(errorMessages[status]);
    }
    return Promise.reject(error);
};

// Response interceptor — unwraps .data automatically
axiosInstance.interceptors.response.use(
    (response: AxiosResponse) => response.data,
    handleResponseError
);

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

/**
 * Make an API request with optional retry logic.
 * @example
 * const data = await apiRequest({ url: '/api/customers', method: 'GET' });
 * const result = await apiRequest({ url: '/api/orders', method: 'POST', data: orderPayload });
 */
export const apiRequest = async <T = unknown>(config: ApiRequestConfig): Promise<T> => {
    const { url, method, maxRetries = 0, delayBetweenRetries = 1000, data, params, headers } = config;
    let attempt = 0;

    while (attempt <= maxRetries) {
        try {
            const response = await axiosInstance.request<T>({ url, method, data, params, headers });
            return response as T;
        } catch (error) {
            if (attempt >= maxRetries) throw error;
            await sleep(delayBetweenRetries);
            attempt++;
        }
    }
    throw new Error('Unexpected end of retry loop');
};

export default apiRequest;
```

## Usage Pattern (in a service or component)
```ts
// filepath: src/services/customerService.ts
import { apiRequest } from '../scripts/apiConnector';
import type { Customer } from '../models/CustomerModels';

export const getCustomers = () =>
    apiRequest<Customer[]>({ url: '/api/customers', method: 'GET' });

export const createCustomer = (payload: Omit<Customer, 'id'>) =>
    apiRequest<Customer>({ url: '/api/customers', method: 'POST', data: payload });

export const updateCustomer = (id: string, payload: Partial<Customer>) =>
    apiRequest<Customer>({ url: `/api/customers/${id}`, method: 'PUT', data: payload });

export const deleteCustomer = (id: string) =>
    apiRequest({ url: `/api/customers/${id}`, method: 'DELETE' });
```

## Rules
1. **NEVER** use `fetch()` directly — always `apiRequest`
2. **NEVER** use `process.env.REACT_APP_*` — always `import.meta.env.VITE_API_BASE_URL`
3. **NEVER** use `$http` — that's AngularJS; replace with `apiRequest`
4. Create a dedicated `src/services/<domain>Service.ts` file for each API domain — never call `apiRequest` directly inside a React component
5. Type all responses: `apiRequest<ResponseType>(...)`
