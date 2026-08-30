# Guide

Standing up monitoring. Fifteen minutes, plus however long you spend deciding
retention.

> **Decide the stack before Production is built.** Every log shipper points at
> whichever one you choose, including the WSO2 gateway sidecars configured in the
> team's own repository. Switching after Production is live means editing that
> repo and redeploying the gateways.

## 1 · Choose the stack

Read the comparison on the Theory tab. If you are unsure:

- **LGTM** if you want traces and metrics in the same place as logs, and your
  team debugs by narrowing to a workload rather than grepping for strings.
- **Elastic** if your team already knows Kibana. It is what this lab has actually
  tested, which makes it the lowest-risk answer for this rollout.
- **OpenSearch** if you want Elasticsearch-style search without the licence
  question.

## 2 · Choose where it runs

In the cluster costs no VMs and is managed like everything else. On a Docker VM it
survives the cluster being broken — which is when you most want to read logs.

## 3 · If you chose LGTM, confirm object storage first

Run **Object storage** and let it finish. This workload creates a bucket and a
scoped service account per component, but the object store itself must be up. The
playbook checks and stops with a clear message rather than leaving three
components crash-looping.

## 4 · Set retention deliberately

Thirty days is the default. Storage scales with it, and you cannot reclaim space
by lowering it later.

## 5 · Run, then verify

The final task confirms every datasource answers. Log in to the dashboard, check
you can see data from both clusters, then specifically check the WSO2 gateway logs
— they route through a sidecar and are the most likely thing to be misconfigured.

## 6 · Point the shippers

Monitoring is not finished when the server is up. Each environment needs its log
shipper installed and pointed here. Anything not shipping is invisible, and you
will not discover which during an incident.
