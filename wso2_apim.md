# WSO2 APIM Setup

## Target Version

- WSO2 API Manager 4.7.0  
- Base image: `wso2/wso2am:4.7.0` [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

## Base Deployment Approach

- Use `wso2/wso2am:4.7.0` as the base image.
- Build a derived custom image for project-specific additions (MSSQL driver, custom JARs, logging config). [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)
- Deploy APIM to Kubernetes from manifests stored in GitLab.
- Let ArgoCD sync APIM manifests into the cluster; Ansible only installs and bootstraps ArgoCD, not APIM itself.
- Keep APIM deployment in the same Git-based Kubernetes model as the rest of the platform (not Docker).

***

## Required Customizations

The APIM image or deployment must include:

1. **Replica topology per environment**
   - Lab: 1 Control Plane (CP) + 1 internal GW + 1 external GW.
   - UAT: 1 CP + 1 internal GW + 1 external GW (acceptable for capacity).
   - Production: 2 CP + 2 internal GW + 2 external GW pods (recommended minimum for production workloads). [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

2. **SQL Server connector (MSSQL JDBC)**
   - Microsoft JDBC Driver for SQL Server **13.4.0**.
   - JAR: `mssql-jdbc-13.4.0.jre11.jar`.
   - Baked into the custom image and added to the APIM classpath.

3. **Custom `log4j2` configuration**
   - Log to **stdout** for container visibility and quick diagnostics.
   - Log to **files under `/repository/logs/`** for structured shipping and long-term retention. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

4. **Custom JARs**
   - JAR for showing the API key list in the admin portal (customer-specific feature).
   - Any other required extensions are added as image layers, not mounted ad hoc. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

5. **Log shipping sidecar**
   - Sidecar container running **Elastic Agent 9.1.4**. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)
   - Shared volume for APIM logs.
   - Output destination: Logstash on the Docker platform (for example `logstash:5044` on the shared Docker network). [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

6. **Kubernetes manifests in GitLab**
   - APIM Deployment/StatefulSet, Services, ConfigMaps, Secrets (where appropriate).
   - Sidecar Pod spec for Elastic Agent.
   - Envoy Gateway routes for external exposure.
   - Stored in GitLab and synced by ArgoCD.

***

## Recommended Packaging Model

Do **not** patch artifacts manually in running containers.

Preferred approach:

1. Start from the official WSO2 subscription image.
2. Add MSSQL JDBC Driver 13.4.0 to the image classpath.
3. Add the custom JARs (key list feature, etc.) into the image.
4. Add `log4j2` override via:
   - ConfigMap-mounted file, or
   - An additional image layer that replaces the default `log4j2` config.
5. Define the Elastic Agent sidecar as a **separate container** in the Pod spec, not merged into the APIM container. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

This keeps the build reproducible, fits the Git + ArgoCD model, and avoids “kubectl edit” style drift.

***

## Logging Design

WSO2 APIM should log to both:

- **stdout** — quick diagnostics via `kubectl logs`.
- **File** — under the standard WSO2 log directory for structured shipping and retention:

```text
/repository/logs/
```

Key files include:

- `wso2carbon.log`
- `wso2-apigw-service.log`
- Rotated log files in the same directory. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

APIM log configuration must ensure:

- All relevant application and gateway logs are present in `/repository/logs/`.
- Log format is stable enough for downstream parsing in Logstash and Elasticsearch.

***

## Log Shipping Sidecar

Use **Elastic Agent 9.1.4** as the default sidecar container for APIM Pods. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

### Shared Volume Model

- Main APIM container writes logs to `/repository/logs/`.
- A shared volume (e.g. `apim-logs`) mounts that directory into both the APIM container and the sidecar.
- Sidecar reads only the required log files and ships them to the observability pipeline.

### Logstash Routing

- Sidecar output should target Logstash on the Docker platform (for example, `logstash:5044` on the shared Docker network).
- Logstash then:
  - Parses WSO2 logs.
  - Routes them into dedicated Elasticsearch indices with 10-year retention policies, distinct from generic logs. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

### Important Caution

If the entire `/repository/logs/` directory is mounted, Elastic Agent will see:

- All rotated logs.
- All noisy or non-essential files.

To control this:

- Use **explicit file paths** in Elastic Agent log inputs (e.g. only `wso2carbon.log`, `wso2-apigw-service.log`).
- Or use `exclude_files` patterns to filter out unwanted logs. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

***

## Observability Notes

WSO2 logs are **not** generic container logs for this platform — they have stronger retention and are operationally more sensitive. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

Recommended behavior:

- Generic OpenTelemetry container logs follow the standard platform log retention policy.
- WSO2 application logs:
  - Are shipped via Elastic Agent sidecar to Logstash.
  - Get dedicated Elasticsearch indices.
  - Have a **10-year** retention policy, aligned with platform compliance requirements. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/244f069b-3095-4613-a675-c71f0fed8b56/vm-requirements.md)

This separates APIM operational audit history from ephemeral workload logs.

***

## Kubernetes and GitLab Automation

WSO2 APIM should live inside the same Kubernetes automation model as the rest of the platform.

### Expected Model

1. **Manifests in GitLab**
   - APIM Deployments/StatefulSets, Services, ConfigMaps, Secrets.
   - Sidecar (Elastic Agent) configuration.
   - Envoy Gateway `HTTPRoute` / `TLSRoute` definitions for APIM external access.

2. **ArgoCD as the deployment engine**
   - ArgoCD installed and managed via Ansible during Kubernetes rollout.
   - APIM manifests stored in GitLab repo(s) watched by ArgoCD.
   - ArgoCD syncs APIM and its sidecar/ingress resources into the cluster.

3. **Python Web UI role**
   - Knows which GitLab repo/branch holds APIM manifests.
   - Can update simple environment-specific values (domains, URLs) by editing templates before commit when needed.
   - Triggers ArgoCD sync indirectly (e.g. via label/annotation or sync API) instead of deploying APIM directly. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

This keeps APIM fully inside the Git + ArgoCD Kubernetes path and avoids treating it as a special case.

***

## Migration Strategy

Use a **fresh WSO2 APIM 4.7 installation** and re-provision application keys from the old 4.4 environment. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

Why this is reasonable:

- Avoids a risky in-place upgrade chain.
- Keeps the new Kubernetes deployment clean.
- Allows controlled re-mapping of existing client credentials without forcing consumer changes.

***

## Migration Method: Fresh 4.7 Install + Key Provisioning

This is a documented, working pattern for migrating credentials from older APIM versions into a fresh 4.x installation. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

### High-Level Flow

1. Enable key provisioning on the new 4.7 APIM instance.
2. Obtain DevPortal API access token.
3. Create applications in 4.7.
4. Map existing client IDs and secrets from 4.4 into the new applications via the `generate-keys` API.

The curl commands in the original doc are **reference examples**, but the MVP should implement this as a **Python job** rather than manual CLI calls.

### Step 1: Enable Key Provisioning on 4.7

Add to `APIM_HOME/repository/conf/deployment.toml`:

```toml
[apim.devportal]
enable_key_provisioning = true
```

Restart APIM after the change. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

### Step 2–4: Automate via Python

Instead of operators manually running curl, implement:

1. **Export application credentials from 4.4**
   - Use WSO2 API or database access to extract:
     - Application name.
     - Throttling policy.
     - Existing `clientId` and `clientSecret`.

2. **Python migration job on the jump host**
   - For each application:
     - Call DevPortal API to create application in 4.7.
     - Call `generate-keys` with the old `clientId` and `clientSecret` mapped to the new `applicationId`.
   - Save:
     - Mapping results.
     - Success/failure status.
     - Any error messages.

3. **State tracking**
   - Store migration results in SQLite or job logs so migration is auditable and resumable. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

If the response confirms the same `consumerKey` and `consumerSecret`, the migrated consumers do not need to change their credentials.

### Not Automated in MVP

Reasonable to keep **manual** (or separate) for now:

- Re-creating APIs on 4.7 via `apictl` or Publisher UI.
- Re-creating API subscriptions per application (IDs differ in the new environment).
- Deciding which legacy applications to migrate first.

***

## Recommended Automation Boundary

The migration flow must **not** remain as manual curl scripts in operations.

Recommended:

- **Python job** (or Ansible orchestration) from the jump host.
- Optional: a button in the Python Web UI that triggers the migration job with target environment + source export location.
- Migration status exposed in the UI as:
  - Number of applications migrated.
  - Errors per application.
  - Whether existing credentials were preserved. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

***

## Suggestions and Risk Areas

This APIM design is aligned with the updated MVP and infrastructure model. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/7add7ea9-5efa-469a-bd8c-5759b4d8f395/wso2_apim.md)

Main things to control:

1. **Image customization reproducibility**
   - Custom image for MSSQL driver and custom JARs must be built from code, not from live containers.
   - Keep a Dockerfile for APIM customization in Git.

2. **Log separation and retention**
   - WSO2 logs must be clearly separated from generic logs at Logstash/Elasticsearch level.
   - Ten-year retention for WSO2 indices must be enforced via ILM policies. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/105021038/244f069b-3095-4613-a675-c71f0fed8b56/vm-requirements.md)

3. **Migration automation**
   - Migration must be a repeatable job, not ad hoc curl.
   - Ensure the Python job can be re-run safely for partial failures.

If those three are handled, APIM will sit cleanly in the overall platform and won’t become the “special snowflake” deployment.