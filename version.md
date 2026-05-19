# Complete Version Matrix

## Purpose

This document defines the target MVP software versions as of May 19, 2026.

Use these versions as the default deployment baseline unless a later reviewed change is approved.

## Pinned Versions

These versions should not change without review.

| Component | Pinned Version | Docker Image | Support Notes |
| --- | --- | --- | --- |
| WSO2 API Manager | 4.7.0 | wso2/wso2am:4.7.0 | Follow WSO2 subscription support policy |
| WSO2 Identity Server | 7.3.0 | wso2/wso2is:7.3.0 | Follow WSO2 subscription support policy |
| Elasticsearch | 9.1.4 | docker.elastic.co/elasticsearch/elasticsearch:9.1.4 | Pinned migration landing version |

## Elastic Stack

All Elastic components must stay aligned to Elasticsearch 9.1.4.

| Component | Version | Docker Image | Support Notes |
| --- | --- | --- | --- |
| Kibana | 9.1.4 | docker.elastic.co/kibana/kibana:9.1.4 | Must match Elasticsearch |
| Logstash | 9.1.4 | docker.elastic.co/logstash/logstash:9.1.4 | Must match Elasticsearch |
| Fleet Server | 9.1.4 | docker.elastic.co/beats/elastic-agent:9.1.4 | Delivered through Elastic Agent |
| APM Server | 9.1.4 | docker.elastic.co/apm/apm-server:9.1.4 | Use only if staying with standalone APM mode |
| Elastic Agent | 9.1.4 | docker.elastic.co/beats/elastic-agent:9.1.4 | Preferred over Filebeat for new deployments |

### Elastic Rule

Do not mix Elasticsearch 9.1.4 with newer Elastic component versions such as 9.4.x.

## GitLab

| Component | Version | Docker Image | Support Notes |
| --- | --- | --- | --- |
| GitLab CE | 18.11.3 | gitlab/gitlab-ce:18.11.3-ce.0 | Keep on the current supported minor line |
| GitLab Runner | 18.11.3 | gitlab/gitlab-runner:v18.11.3 | Keep aligned to GitLab CE minor version |

## Code Quality

| Component | Version | Docker Image | Support Notes |
| --- | --- | --- | --- |
| SonarQube with community branch plugin | 26.4.0.121862 | mc1arke/sonarqube-with-community-branch-plugin:26.4.0.121862-community | Keep plugin and SonarQube release aligned |
| PostgreSQL for SonarQube | 17.10 | postgres:17.10 | Dedicated SonarQube backing database |

## Mail

| Component | Version | Docker Image | Support Notes |
| --- | --- | --- | --- |
| Stalwart SMTP | v0.16.5 | stalwartlabs/stalwart:v0.16.5 | Rolling release project |

## Alerting and Deployment

| Component | Version | Docker Image | Support Notes |
| --- | --- | --- | --- |
| ElastAlert2 | 2.29.0 | jertel/elastalert2:2.29.0 | Community-maintained |
| Dokploy | v0.29.4 | dokploy/dokploy:v0.29.4 | Keep at or above the reviewed security-fixed release |

## Networking and Ingress

| Component | Version | Docker Image | Support Notes |
| --- | --- | --- | --- |
| Traefik | v3.7.1 | traefik:v3.7.1 | Use the current v3 line |
| Envoy Gateway | v1.8.0 | docker.io/envoyproxy/gateway:v1.8.0 | Track its shorter support window |

## Kubernetes Infrastructure

| Component | Version | Helm or Image | Support Notes |
| --- | --- | --- | --- |
| Omni | v1.7.3 | ghcr.io/siderolabs/omni:v1.7.3 | Self-hosted control plane for Talos |
| cert-manager | v1.20.2 | jetstack/cert-manager v1.20.2 | Use the current supported release line |
| ArgoCD | v3.4.2 | quay.io/argoproj/argocd:v3.4.2 | Avoid the already-EOL 3.1 line |

## Observability

| Component | Version | Docker Image | Support Notes |
| --- | --- | --- | --- |
| OpenTelemetry Collector | v0.152.0 | otel/opentelemetry-collector-contrib:0.152.0 | Rolling release project |

## Automation and Runtime

| Component | Version | Runtime or Image | Support Notes |
| --- | --- | --- | --- |
| ansible-core | 2.20.6 | Control node install or container image | Use this instead of older 2.18.x lines |
| ansible-runner | 2.4.3 | Pip or control image | Keep aligned with ansible-core support |
| Python runtime | 3.13.13 | python:3.13.13-slim | Web UI and automation runtime |

## EOL Watchlist

| Component | Watch Item | Action |
| --- | --- | --- |
| GitLab 18.11 | Will age out behind newer release lines quickly | Plan a 19.x review after MVP stabilization |
| Envoy Gateway v1.8 | Shorter support window | Plan the next review cycle in Q3 |
| SonarQube branch plugin line | Plugin must match SonarQube release family | Do not upgrade SonarQube alone |
| ansible-core 2.18 | Already too old for this baseline | Do not use it |
| ArgoCD 3.1 | Already EOL | Do not use it |

## Compatibility Rules

Before deployment, verify the following:

1. Elastic stack components all remain on 9.1.4.
2. Elastic Agent sidecar or any standalone Beats output remains compatible with Logstash and Elasticsearch 9.1.4.
3. WSO2 APIM 4.7.0 and WSO2 IS 7.3.0 remain compatible with the selected SQL Server connector and Kubernetes deployment model.
4. GitLab CE 18.11.3 and GitLab Runner 18.11.3 remain aligned.
5. SonarQube and the community branch plugin remain on the same supported plugin family.
6. The Python web UI dependencies remain compatible with Python 3.13.13 and ansible-runner 2.4.3.

## Python Web UI Template Update Rule

Before deployment sources are pushed to GitLab, the Python web UI must update the Docker Compose YAML templates with the environment-specific values collected from the operator.

### Required behavior

1. Load the base compose template from the repository
2. Apply environment-specific values such as hostnames, ports, image tags, storage paths, external endpoints, and version tags
3. Render the final deployment-ready compose YAML
4. Save or stage the rendered output in the working repository
5. Push the updated compose files to the target GitLab repository
6. Trigger Dokploy deployment from the GitLab source

## Recommendation

Treat this file as the single version source of truth for the MVP.

When a version changes after review, update this file first and then update the affected compose templates, Kubernetes YAML, and automation code.