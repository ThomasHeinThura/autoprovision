# WSO2 APIM Setup

## Target Version

- WSO2 API Manager 4.7.0
- Base image: `wso2/wso2am:4.7.0`

## Base Deployment Approach

- Use `wso2/wso2am:4.7.0` as the base image
- Build a derived custom image for project-specific additions
- Deploy APIM to Kubernetes from YAML stored in GitLab
- Keep the deployment automated through the same Git-first flow as the rest of the platform

## Required Customizations

The APIM image or deployment should include the following:

1. 2 CP + 2 internal GW + 2 external GW pods for high availability. This is the recommended minimum for production workloads.
2. SQL Server connector added to the image, since SQL Server is the chosen database for this platform.
3. Custom `log4j2` configuration to write logs to both stdout and file, so that logs are visible in the container and also structured for shipping.
4. Custom JAR for showing the API key list in the admin portal, as per your requirement.
5. A sidecar container running Elastic Agent 9.1.4 to ship logs to the observability pipeline.
6. Kubernetes YAML stored in GitLab for GitOps-driven deployment and management.

## Recommended Packaging Model

Do not patch these artifacts manually in a running container.

Preferred approach:

1. Start from the official WSO2 subscription image
2. Add the SQL Server connector in the custom image
3. Add the custom JAR in the custom image
4. Add the `log4j2` override through mounted config or image layer
5. Keep the sidecar separate in the Kubernetes pod spec

This is cleaner, reproducible, and compatible with GitLab-driven automation.

## Logging Design

WSO2 APIM should log to both:

- stdout for container visibility and quick diagnostics
- file under the WSO2 log directory for structured shipping and retention

### Expected log location

WSO2 APIM writes logs into:

```text
/repository/logs/
```

This includes files such as:

- `wso2carbon.log`
- `wso2-apigw-service.log`
- rolled log files in the same directory

## Log Shipping Sidecar

Use Elastic Agent 9.1.4 as the default sidecar container.

### Recommended shared volume model

- Main APIM container writes logs to `/repository/logs/`
- Shared volume exposes that log directory to the sidecar
- Sidecar ships selected logs to the observability pipeline

### Important caution

If the entire log directory is mounted into a shared volume, the sidecar will see all log files, including rotated files and noise logs.

Because of that, do one of these:

1. Use explicit file paths in the agent log input configuration
2. Use `exclude_files` patterns to filter out unnecessary logs

### Recommendation

Prefer:

- Elastic Agent 9.1.4 sidecar
- Ship to Logstash first
- Let Logstash route WSO2 logs into the correct Elasticsearch indices and retention policies

That matches the wider design better than sending WSO2 logs directly from the pod to Elasticsearch.

## Observability Notes

For this platform, WSO2 logs should be treated separately from generic container logs.

Recommended behavior:

- Generic OpenTelemetry container logs follow the standard container log retention policy
- WSO2 application logs are shipped through Elastic Agent to Logstash
- WSO2 logs get their own index strategy and 10-year retention path

## Kubernetes and GitLab Automation

WSO2 APIM should be part of the automated Git flow.

### Expected model

1. Store Kubernetes YAML in GitLab
2. Store APIM image version and config references in GitLab
3. Store sidecar configuration in GitLab
4. Let the Python web UI clone or update the repo as needed
5. Push changes to GitLab
6. Deploy through Ansible, ArgoCD, or the agreed Kubernetes automation path

This fits the current platform direction and avoids treating WSO2 as a special manual island.

## Migration Strategy

Use a fresh WSO2 APIM 4.7 installation and re-provision application keys from the old environment.

This is the right direction for your case.

Why it is reasonable:

- It avoids a risky in-place upgrade chain
- It lets you keep the new Kubernetes deployment clean
- It allows controlled re-mapping of existing client credentials

## Migration Method: Fresh 4.7 Install + Key Provisioning

This is a documented working approach for migrating credentials from older APIM versions into a fresh 4.x installation.

### Step 1: Enable key provisioning on 4.7

Add this to `APIM_HOME/repository/conf/deployment.toml` on the new 4.7 instance:

```toml
[apim.devportal]
enable_key_provisioning = true
```

Restart APIM after making the change.

### Step 2: Get an API access token

First, register a DCR client to call the DevPortal REST API:

```bash
curl -X POST -H "Authorization: Basic YWRtaW46YWRtaW4=" \
  -H "Content-Type: application/json" \
  https://localhost:9443/client-registration/v0.17/register \
  -d '{"callbackUrl":"www.example.com","clientName":"rest_api_devportal", \
       "owner":"admin","grantType":"client_credentials password refresh_token", \
       "saasApp":true}'
```

Then get an access token using the returned `clientId:clientSecret` value encoded in base64:

```bash
curl -X POST https://localhost:9443/oauth2/token \
  -H "Authorization: Basic <base64(clientId:clientSecret)>" \
  -d 'grant_type=password&username=admin&password=admin&scope=apim:app_manage apim:subscribe apim:admin'
```

### Step 3: Create the application

```bash
curl -X POST https://localhost:9443/api/am/devportal/v3/applications \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"YourAppName","throttlingPolicy":"Unlimited", \
       "description":"Migrated app","tokenType":"JWT"}'
```

Record the `applicationId` from the response.

### Step 4: Map the old client ID and client secret

Pass the existing client credentials from the old 4.4 environment:

```bash
curl -X POST \
  https://localhost:9443/api/am/devportal/v3/applications/<applicationId>/generate-keys \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "keyType": "PRODUCTION",
    "keyManager": "Resident Key Manager",
    "grantTypesToBeSupported": ["password", "client_credentials"],
    "callbackUrl": "https://client.example.org/callback",
    "scopes": ["am_application_scope", "default"],
    "clientId": "<OLD_CLIENT_ID_FROM_4.4>",
    "clientSecret": "<OLD_CLIENT_SECRET_FROM_4.4>",
    "additionalProperties": {}
  }'
```

If the response confirms the same `consumerKey` and `consumerSecret`, the migrated consumers do not need to change their credentials.

## What This Migration Does Not Automate

| Manual or separate task | Why |
| --- | --- |
| Re-create APIs on 4.7 through `apictl` or Publisher UI | APIs are separate from applications |
| Re-create API subscriptions per application | Subscriptions point to API IDs that differ in the new environment |
| Loop through all applications | The migration API call is per application, even if fully scriptable |

## Recommended Automation Boundary

The migration flow should not stay as manual curl commands in operations.

Recommended implementation:

1. Export application credentials from 4.4 through API or database access
2. Run a Python migration job from the jump host
3. Create applications in 4.7 automatically
4. Call `generate-keys` with the old credentials automatically
5. Save migration results in SQLite or job logs

If there are dozens of applications, this should be scripted from the start.

## Suggestions

Your APIM setup is on the right path. The main suggestions are:

1. Use the official WSO2 image only as a base, then build one controlled custom image for the SQL connector and custom JAR.
2. Keep log shipping explicit. Do not let the sidecar blindly ship every file in `/repository/logs/`.
3. Route WSO2 logs through Logstash rather than directly to Elasticsearch, because your retention policy for WSO2 logs is much longer than generic platform logs.
4. Keep WSO2 Kubernetes YAML in GitLab so APIM and IS stay inside the same automation model as the rest of the platform.
5. Turn the credential migration flow into a Python or Ansible-driven job rather than operator-run curl commands.

## Overall Assessment

The setup is technically sound for an MVP.

The main risk areas are not APIM itself. They are:

- keeping the image customization reproducible
- separating WSO2 logs from generic container logs
- automating the migration workflow enough to avoid manual drift

If you control those three areas, the APIM design should fit the rest of the platform well.