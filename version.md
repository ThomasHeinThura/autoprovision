# Complete Version Matrix

## Purpose

This document defines the target MVP software versions as of May 2026.

Use these versions as the default deployment baseline unless a later reviewed change is approved.

---

## Pinned Versions

These versions should not change without review.

| Component            | Pinned Version | Docker Image                                        | Support Notes                           |
| -------------------- | -------------- | --------------------------------------------------- | --------------------------------------- |
| WSO2 API Manager     | 4.7.0          | wso2/wso2am:4.7.0                                   | Follow WSO2 subscription support policy |
| WSO2 Identity Server | 7.3.0          | wso2/wso2is:7.3.0                                   | Follow WSO2 subscription support policy |
| Elasticsearch        | 9.1.4          | docker.elastic.co/elasticsearch/elasticsearch:9.1.4 | Pinned migration landing version        |

---

## Talos and Kubernetes

| Component    | Version | Notes                                    |
| ------------ | ------- | ---------------------------------------- |
| Talos OS     | v1.13.3 | Base OS for all Kubernetes nodes         |
| Kubernetes   | 1.36.1  | Shipped with Talos v1.13.3               |
| Linux kernel | 6.18.33 | Shipped with Talos v1.13.3               |
| containerd   | 2.2.4   | Shipped with Talos v1.13.3               |
| Go runtime   | 1.26.3  | Talos build runtime — informational only |

---

## Cilium

| Component | Version | Notes                                                                   |
| --------- | ------- | ----------------------------------------------------------------------- |
| Cilium    | 1.19.4  | CNI for Talos Kubernetes cluster. Must be deployed before any workload. |

---

## Elastic Stack

All Elastic components must stay aligned to Elasticsearch 9.1.4.

| Component     | Version | Docker Image                                        | Support Notes                                |
| ------------- | ------- | --------------------------------------------------- | -------------------------------------------- |
| Kibana        | 9.1.4   | docker.elastic.co/kibana/kibana:9.1.4               | Must match Elasticsearch                     |
| Logstash      | 9.1.4   | docker.elastic.co/logstash/logstash:9.1.4           | Must match Elasticsearch                     |
| Fleet Server  | 9.1.4   | docker.elastic.co/beats/elastic-agent:9.1.4         | Delivered through Elastic Agent              |
| APM Server    | 9.1.4   | docker.elastic.co/apm/apm-server:9.1.4              | Use only if staying with standalone APM mode |
| Elastic Agent | 9.1.4   | docker.elastic.co/beats/elastic-agent:9.1.4         | Preferred over Filebeat for new deployments  |

### Elastic Rule

Do not mix Elasticsearch 9.1.4 with newer Elastic component versions such as 9.4.x.

---

## GitLab

| Component     | Version | Docker Image                        | Support Notes                            |
| ------------- | ------- | ----------------------------------- | ---------------------------------------- |
| GitLab CE     | 19.0.1  | gitlab/gitlab-ce:19.0.1-ce.0        | Keep on the current supported minor line |
| GitLab Runner | 19.0.1  | gitlab/gitlab-runner:v19.0.1        | Keep aligned to GitLab CE minor version  |

---

## Code Quality

| Component                              | Version       | Docker Image                                                           | Support Notes                             |
| -------------------------------------- | ------------- | ---------------------------------------------------------------------- | ----------------------------------------- |
| SonarQube with community branch plugin | 26.4.0.121862 | mc1arke/sonarqube-with-community-branch-plugin:26.4.0.121862-community | Keep plugin and SonarQube release aligned |

---

## Shared Database

One shared PostgreSQL instance for GitLab, SonarQube, and platform state.

| Component                    | Version | Docker Image   | Support Notes                                          |
| ---------------------------- | ------- | -------------- | ------------------------------------------------------ |
| PostgreSQL (shared instance) | 17.10   | postgres:17.10 | Single shared backend for GitLab, SonarQube, and state |

---

## Alerting and Management

| Component   | Version | Docker Image              | Support Notes                                          |
| ----------- | ------- | ------------------------- | ------------------------------------------------------ |
| ElastAlert2 | 2.29.0  | jertel/elastalert2:2.29.0 | Community-maintained                                   |
| Dockhand    | v0.29.4 | dockhand/dockhand:v0.29.4 | Docker container management and resource monitoring UI |

---

## Docker Networking and Ingress

Traefik is the ingress layer for the Docker platform only.

| Component | Version | Docker Image   | Support Notes           |
| --------- | ------- | -------------- | ----------------------- |
| Traefik   | v3.7.1  | traefik:v3.7.1 | Use the current v3 line |

### Docker Network Rule

1. Use one shared Docker network for all Docker platform services.
2. Expose all Docker platform HTTPS traffic through Traefik on port 443 only.

---

## Kubernetes Networking and Ingress

Envoy Gateway is the ingress layer for Kubernetes workloads only.

| Component     | Version | Helm or Image                       | Support Notes                    |
| ------------- | ------- | ----------------------------------- | -------------------------------- |
| Envoy Gateway | v1.8.0  | docker.io/envoyproxy/gateway:v1.8.0 | Track its shorter support window |

---

## Kubernetes Infrastructure

| Component    | Version | Helm Chart or Image                | Support Notes                                                                    |
| ------------ | ------- | ---------------------------------- | -------------------------------------------------------------------------------- |
| Headlamp     | v1.7.3  | ghcr.io/siderolabs/headlamp:v1.7.3 | Deploy via Sidero-provided Helm chart. Talos-native RBAC and API access pre-configured. |
| cert-manager | v1.20.2 | jetstack/cert-manager v1.20.2      | Use the current supported release line                                           |
| ArgoCD       | v3.4.2  | quay.io/argoproj/argocd:v3.4.2     | Avoid the already-EOL 3.1 line                                                   |

---

## Observability

| Component               | Version  | Docker Image                                 | Support Notes           |
| ----------------------- | -------- | -------------------------------------------- | ----------------------- |
| OpenTelemetry Collector | v0.152.0 | otel/opentelemetry-collector-contrib:0.152.0 | Rolling release project |

---

## WSO2 Custom Image Dependencies

These are added to the WSO2 custom image at build time and are not separate container deployments.

| Component             | Version | Artifact                    | Notes                                                                                      |
| --------------------- | ------- | --------------------------- | ------------------------------------------------------------------------------------------ |
| Microsoft JDBC Driver | 13.4.0  | mssql-jdbc-13.4.0.jre11.jar | Latest GA. Supports Java 8, 11, 17, 21, 25. Use jre11 jar for WSO2 APIM 4.7.0 on Java 17. |

---

## Automation and Runtime

| Component      | Version | Runtime or Image     | Support Notes                           |
| -------------- | ------- | -------------------- | --------------------------------------- |
| ansible-core   | 2.20.6  | Control node install | Use this instead of older 2.18.x lines  |
| ansible-runner | 2.4.3   | Pip or control image | Keep aligned with ansible-core support  |
| Python runtime | 3.13.13 | python:3.13.13-slim  | Web UI and automation runtime           |

---

## EOL Watchlist

| Component               | Watch Item                                      | Action                                           |
| ----------------------- | ----------------------------------------------- | ------------------------------------------------ |
| GitLab 19.0             | Monitor for patch releases on the 19.x line     | Stay current on 19.x patch versions              |
| Envoy Gateway v1.8      | Shorter support window                          | Plan next review cycle in Q3                     |
| SonarQube branch plugin | Plugin must match SonarQube release family      | Do not upgrade SonarQube alone                   |
| ansible-core 2.18       | Already too old for this baseline               | Do not use it                                    |
| ArgoCD 3.1              | Already EOL                                     | Do not use it                                    |

---

## Compatibility Rules

Before deployment, verify the following:

1. Elastic stack components all remain on 9.1.4.
2. Elastic Agent sidecar output remains compatible with Logstash and Elasticsearch 9.1.4.
3. WSO2 APIM 4.7.0 and WSO2 IS 7.3.0 remain compatible with MSSQL JDBC 13.4.0 and the Kubernetes deployment model.
4. GitLab CE 19.0.1 and GitLab Runner 19.0.1 remain aligned.
5. SonarQube and the community branch plugin remain on the same supported plugin family.
6. Python web UI dependencies remain compatible with Python 3.13.13 and ansible-runner 2.4.3.
7. Cilium 1.19.4 remains compatible with Kubernetes 1.36.1 and Talos v1.13.3.
8. Envoy Gateway v1.8.0 is used for Kubernetes ingress only. Traefik v3.7.1 is used for Docker platform ingress only. Do not mix their responsibilities.

---

## Python Web UI Template Update Rule

Before deployment is triggered, the Python web UI must render Docker Compose YAML templates with environment-specific values collected from the operator.

### Required Behavior

1. Load the base compose template from the repository
2. Apply environment-specific values — hostnames, ports, image tags, storage paths, external endpoints, version tags
3. Render the final deployment-ready compose YAML
4. Save or stage the rendered output in the working repository
5. Push the updated compose files to the GitLab repository
6. Trigger Ansible deployment from the jump host

---

## Recommendation

Treat this file as the single version source of truth for the MVP.

When a version changes after review, update this file first, then update the affected compose templates, Kubernetes YAML, and automation code.
