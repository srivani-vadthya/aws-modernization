"""Wave-1 motor-policy Spring Boot skeleton written into the artifact pack."""

from __future__ import annotations

from pathlib import Path

POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.nexus.insurance</groupId>
  <artifactId>motor-policy-service</artifactId>
  <version>0.1.0</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.5</version>
  </parent>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
    </dependency>
    <dependency>
      <groupId>org.flywaydb</groupId>
      <artifactId>flyway-core</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
"""

APP = """package com.nexus.insurance.motor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MotorPolicyApplication {
  public static void main(String[] args) {
    SpringApplication.run(MotorPolicyApplication.class, args);
  }
}
"""

CTRL = """package com.nexus.insurance.motor.api;

import com.nexus.insurance.motor.domain.BindMotorPolicy;
import com.nexus.insurance.motor.domain.MotorPolicy;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/policies/motor")
public class MotorPolicyController {
  private final BindMotorPolicy bind;

  public MotorPolicyController(BindMotorPolicy bind) {
    this.bind = bind;
  }

  @PostMapping
  @ResponseStatus(HttpStatus.CREATED)
  public MotorPolicy create(@RequestBody MotorPolicy request) {
    return bind.execute(request);
  }
}
"""

DOMAIN = """package com.nexus.insurance.motor.domain;

public record MotorPolicy(
    String policyId,
    String customerId,
    String vehicleReg,
    String coverType,
    long premiumCents
) {}
"""

USECASE = """package com.nexus.insurance.motor.domain;

import com.nexus.insurance.motor.events.DomainEventPublisher;
import com.nexus.insurance.motor.events.PolicyBound;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class BindMotorPolicy {
  private final MotorPolicyRepository policies;
  private final DomainEventPublisher events;

  public BindMotorPolicy(MotorPolicyRepository policies, DomainEventPublisher events) {
    this.policies = policies;
    this.events = events;
  }

  @Transactional
  public MotorPolicy execute(MotorPolicy request) {
    var id = request.policyId() == null || request.policyId().isBlank()
        ? UUID.randomUUID().toString()
        : request.policyId();
    var saved = new MotorPolicy(id, request.customerId(), request.vehicleReg(), request.coverType(), request.premiumCents());
    policies.save(saved);
    events.publish(new PolicyBound(id, request.customerId()));
    return saved;
  }
}
"""

REPO = """package com.nexus.insurance.motor.domain;

public interface MotorPolicyRepository {
  MotorPolicy save(MotorPolicy policy);
}
"""

EVENT = """package com.nexus.insurance.motor.events;

public record PolicyBound(String policyId, String customerId) {}
"""

PUB = """package com.nexus.insurance.motor.events;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class DomainEventPublisher {
  private static final Logger log = LoggerFactory.getLogger(DomainEventPublisher.class);

  public void publish(PolicyBound event) {
    // Outbox + EventBridge adapter is generated in CDK, not in the domain.
    log.info("event=PolicyBound policyId={} customerId={}", event.policyId(), event.customerId());
  }
}
"""

FLYWAY = """CREATE TABLE customer (
  customer_id VARCHAR(36) PRIMARY KEY,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  date_of_birth DATE
);

CREATE TABLE motor_policy (
  policy_id VARCHAR(36) PRIMARY KEY,
  customer_id VARCHAR(36) NOT NULL REFERENCES customer(customer_id),
  vehicle_reg TEXT NOT NULL,
  cover_type TEXT NOT NULL,
  premium_cents BIGINT NOT NULL,
  status TEXT NOT NULL DEFAULT 'BOUND'
);

CREATE TABLE outbox (
  id UUID PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ
);
"""

README = """# motor-policy-service

Wave-1 reimagine of IBM CICS GenApp motor policy (LGAPOL01 / LGAPDB01 / LGIPOL01 / LGDPOL01).

- Java 21 / Spring Boot 3 / hexagonal modules
- Aurora PostgreSQL via Flyway
- Domain events: PolicyBound (CloudEvents envelope at the adapter)

Generated by Nexus Modernize. AWS Transform reimagine artifacts sit alongside this skeleton.
"""

FILES = {
    "pom.xml": POM,
    "README.md": README,
    "src/main/java/com/nexus/insurance/motor/MotorPolicyApplication.java": APP,
    "src/main/java/com/nexus/insurance/motor/api/MotorPolicyController.java": CTRL,
    "src/main/java/com/nexus/insurance/motor/domain/MotorPolicy.java": DOMAIN,
    "src/main/java/com/nexus/insurance/motor/domain/BindMotorPolicy.java": USECASE,
    "src/main/java/com/nexus/insurance/motor/domain/MotorPolicyRepository.java": REPO,
    "src/main/java/com/nexus/insurance/motor/events/PolicyBound.java": EVENT,
    "src/main/java/com/nexus/insurance/motor/events/DomainEventPublisher.java": PUB,
    "src/main/resources/db/migration/V1__motor.sql": FLYWAY,
}


def write_generated(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for rel, content in FILES.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
