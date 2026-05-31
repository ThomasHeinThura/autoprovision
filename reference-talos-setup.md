I’ve been meaning to set up a Talos linux kubernetes cluster in my homelab for a while and set one up over the holiday break. Here’s how I did it.

All the blogs and videos I looked at used the nginx ingress, which would be fine, except that the nginx ingress is a dead man walking and will be unsupported starting in March of 2026. No patches, no security updates, completely unsupported.

Based on some advice on the hangops slack (Thanks, Brandon!) I wanted to use Cilium since it supports the Gateway API and can also do ARP announcements like MetallB.

This is part one of a series I’m writing as I get my new homelab cluster up and running.

Part 1 - Creating a Talos cluster with a Cilium CNI on Proxmox
Part 2 - Add SSL to Kubernetes using Cilium, cert-manager and LetsEncrypt with domains hosted on Amazon Route 53
Part 3 - Set up Secret Management with SOPS
Part 4 - Back up your Talos etcd cluster to a SMB share
Part 5 - Install ArgoCD
Part 6 - Install MQTT into a k8s cluster
Part 7 - Add an ArgoCD git generator ApplicationSet
Part 8 - Add Traefik to the cluster
Pre-requisites
proxmox will make it easier to rebuild your cluster if you make a mistake, but these instructions will work with bare metal as well.
cilium, kubectl & helm cli tools. If you don’t want to brew install them or are not using a Mac, installation instructions are at cilium.io, helm.sh and kubectl.
Software Versions
Here are the versions of the software I used while writing this post. Later versions should work, but this is what these instructions were tested with.

Software	Version
cilium	1.18.6
helm	4.0.1
kubectl	1.34
kubernetes	1.34.1
talos	1.11.5
Let’s get started.

Create a Proxmox VM control plane node
There are a ton of videos and blogs describing getting started with proxmox, so I’m not going to go into a lot of detail here. The TL;DR is:

Go to the Talos image factory.
Create an image.
Start with the Cloud Server option
Select the latest Talos version
Pick nocloud from the cloud type screen since it explicitly mentions proxmox in the description
Select your architecture
You should now be on the System Extensions page. Pick qemu-guest-agent and util-linux-tools
Pick auto for the bootloader.
You should now see Schematic Ready. Copy the ISO link
Download the ISO into your Proxmox host’s ISO storage
Start a new VM with at least 4 CPUs, 4 GB of RAM and at least a 16GB drive. Make sure you enable the qemu agent. If you’re planning to use this for real workloads later, you’ll want to go bigger - have a look at Sidero’s System Requirements page. I went with 100G per their recommendations.
Wait until the Talos Dashboard appears, then copy the new node’s IP address
On your DHCP server, find the IP from step 6, and set that as a static assignment. The server will reboot multiple times during installation, and if it changes IP you will have to update your kubeconfig and talosconfig files. If it changes IP addresses after you add a worker node, things will break so spare yourself future aggravation and give it a static assignment from the beginning.
Once the Talos dashboard on the VM console shows that is in maintenance mode you can start to configure it. Again, make sure your DHCP is assigning it a static IP, that will save you aggravation later.

We’re going to make a single node cluster to simplify things since it’s just for learning. You can add worker nodes later very easily once you want to put real workloads in the cluster.

Configure the cluster control plane
Setup some environment variables
Set CLUSTER_NAME and CONTROL_PLANE_IP environment variables to make copying commands from this post easier.

export CLUSTER_NAME=sisyphus
export CONTROL_PLANE_IP=10.0.1.51
Find out what disks are on the server
The Talos installer needs to know what device is the node’s hard drive, so use talosctl to get the available disks.

talosctl get disks --insecure --nodes "$CONTROL_PLANE_IP"
You’ll see something like

NODE        NAMESPACE   TYPE   ID      VERSION   SIZE     READ ONLY   TRANSPORT   ROTATIONAL   WWID   MODEL           SERIAL
10.0.1.51   runtime     Disk   loop0   2         73 MB    true
10.0.1.51   runtime     Disk   sda     2         17 GB    false       virtio      true                QEMU HARDDISK
10.0.1.51   runtime     Disk   sr0     2         317 MB   false       ata         true                QEMU DVD-ROM    QEMU_DVD-ROM_QM00003
Our node’s hard drive is sda, so

export DISK_NAME=sda
Create a cluster patch file
We’re going to use Cilium as the CNI and also have it replace kube-proxy, so let’s create the cluster with no CNI and disable kube-proxy. To do that, we’re going to create a patch file we can use when we generate the cluster’s configuration with talosctl.

# cluster-patch.yaml
cluster:
  network:
    cni:
      name: none
  proxy: # Disable kube-proxy, Cilium will replace it too
    disabled: true
Generate the talos configuration
talosctl gen config $CLUSTER_NAME "https://$CONTROL_PLANE_IP:6443" --install-disk "/dev/$DISK_NAME" --config-patch @cluster-patch.yaml
export TALOSCONFIG="$(pwd)/talosconfig"
Initialize the cluster
I like to test things in short-lived clusters so I don’t have to worry about breaking things that my internal services depend on. I like naming nodes clustername-role-number so that when I look at their proxmox console, it’s nice and clear what cluster the node is in and what its role is.

Here’s how to create a patch file that sets the node name when we apply our configuration. We also want to enable scheduling on the control plane node since we’re setting up a single-node cluster.

Create a controlplane-1-patch.yaml that includes the hostname you want and sets allowSchedulingOnControlPlanes to true.

# controlplane-1-hostname-patch.yaml
machine:
  network:
    hostname: sisyphus-cn-1
cluster:
  allowSchedulingOnControlPlanes: true
Apply the configuration to your control plane node to initialize the cluster with the merged controlpane.yaml and controlplane-1-patch.yaml files.

talosctl apply-config --insecure \
  --nodes $CONTROL_PLANE_IP \
  --file controlplane.yaml \
  --insecure \
  --config-patch @controlplane-1-patch.yaml
Bootstrap etcd in the cluster
ONLY DO THIS ONCE! Wait until you see etcd is waiting to join the cluster in the bottom portion of the dashboard. Depending on how fast your proxmox host is, this can take 5-10 minutes.

There will be some error messages and it will look like nothing is happening, be patient it will get back to ready. I think this is because we’re configuring the cluster to not include a CNI so we can use Cilium, and/or because we disable kube-proxy because Cilium replaces that functionality too.

The first time I stood a cluster up without CNI it took long enough that I thought I’d broken the configuration - it wasn’t till I kicked it off and then went to cook dinner that I gave it enough time to settle down.

So be patient, at least you only have to do this once per cluster.

talosctl bootstrap --nodes "$CONTROL_PLANE_IP" --talosconfig=./talosconfig
Create a kubeconfig file
talosctl kubeconfig sisyphus-kubeconfig --nodes $CONTROL_PLANE_IP --talosconfig=./talosconfig
export KUBECONFIG="$(pwd)/sisyphus-kubeconfig"
Confirm that the cluster came up
kubectl get nodes
You’ll see something similar to

NAME              STATUS   ROLES           AGE     VERSION   INTERNAL-IP   EXTERNAL-IP   OS-IMAGE          KERNEL-VERSION   CONTAINER-RUNTIME
sisyphus-cn-1     Ready    control-plane   5m      v1.34.1   10.0.1.51     <none>        Talos (v1.11.5)   6.12.57-talos    containerd://2.1.5
Install cilium
First install the CRDs
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_gatewayclasses.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_gateways.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_httproutes.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_referencegrants.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_grpcroutes.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/experimental/gateway.networking.k8s.io_tlsroutes.yaml
Confirm the gateway classes are present
kubectl get crd gatewayclasses.gateway.networking.k8s.io gateways.gateway.networking.k8s.io httproutes.gateway.networking.k8s.io
You should see something like this:

NAME                                       CREATED AT
gatewayclasses.gateway.networking.k8s.io   2026-01-02T04:20:13Z
gateways.gateway.networking.k8s.io         2026-01-02T04:20:14Z
httproutes.gateway.networking.k8s.io       2026-01-02T04:20:15Z
Set up the cilium helm repo
helm repo add cilium https://helm.cilium.io/
helm repo update
Install cilium
cilium install \
  --version 1.18.1 \
  --helm-set=ipam.mode=kubernetes \
  --helm-set=kubeProxyReplacement=true \
  --helm-set=securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
  --helm-set=securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
  --helm-set=cgroup.autoMount.enabled=false \
  --helm-set=cgroup.hostRoot=/sys/fs/cgroup \
  --helm-set=l2announcements.enabled=true \
  --helm-set=externalIPs.enabled=true \
  --set gatewayAPI.enabled=true \
  --helm-set=devices=e+ \
  --helm-set=operator.replicas=1
You’ll see something like

ℹ️  Using Cilium version 1.18.1
🔮 Auto-detected cluster name: sisyphus
🔮 Auto-detected kube-proxy has not been installed
ℹ️  Cilium will fully replace all functionalities of kube-proxy
I0101 21:25:52.110400   48637 warnings.go:110] "Warning: spec.SessionAffinity is ignored for headless services"
This took several minutes to come up on my sisyphus cluster controller with 2 cores and 4GB RAM

Confirm cilium status
Confirm that Cilium is fully up and has no errors.

❯ cilium status
    /¯¯\
 /¯¯\__/¯¯\    Cilium:             OK
 \__/¯¯\__/    Operator:           OK
 /¯¯\__/¯¯\    Envoy DaemonSet:    OK
 \__/¯¯\__/    Hubble Relay:       disabled
    \__/       ClusterMesh:        disabled

DaemonSet              cilium                   Desired: 1, Ready: 1/1, Available: 1/1
DaemonSet              cilium-envoy             Desired: 1, Ready: 1/1, Available: 1/1
Deployment             cilium-operator          Desired: 1, Ready: 1/1, Available: 1/1
Containers:            cilium                   Running: 1
                       cilium-envoy             Running: 1
                       cilium-operator          Running: 1
                       clustermesh-apiserver
                       hubble-relay
Cluster Pods:          2/2 managed by Cilium
Helm chart version:    1.18.1
Image versions         cilium             quay.io/cilium/cilium:v1.18.1@sha256:65ab17c052d8758b2ad157ce766285e04173722df59bdee1ea6d5fda7149f0e9: 1
                       cilium-envoy       quay.io/cilium/cilium-envoy:v1.34.4-1754895458-68cffdfa568b6b226d70a7ef81fc65dda3b890bf@sha256:247e908700012f7ef56f75908f8c965215c26a27762f296068645eb55450bda2: 1
                       cilium-operator    quay.io/cilium/operator-generic:v1.18.1@sha256:97f4553afa443465bdfbc1cc4927c93f16ac5d78e4dd2706736e7395382201bc: 1
Update talosconfig
The beginning of your talosconfig file will start with something like this:

context: sisyphus
contexts:
    sisyphus:
        endpoints:
            - 10.0.1.51
        ca: 
Update it to include a nodes entry

context: sisyphus
contexts:
    sisyphus:
        endpoints:
            - 10.0.1.51
        nodes:
            - 10.0.1.51
        ca: 
This will keep you from contantly having to specify --nodes for your talosctl commands.

Confirm that the cluster is showing healthy
talosctl health
Check external connectivity to cluster services
First, test a LoadBalancer service
Make a playground directory and put the following files in it.

Create the playground namespace
# 01-create-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  labels:
    kubernetes.io/metadata.name: playground
  name: playground
Create an IP Pool and Announcement Policy
# 02-cilium-setup.yaml
# Create our list of IPs
apiVersion: "cilium.io/v2alpha1"
kind: CiliumLoadBalancerIPPool
metadata:
  name: "default-pool"
spec:
  blocks:
  - start: "10.0.1.160" # Use IPs that are outside of your DHCP range but on
    stop: "10.0.1.170"  # the same /24 as your talos VM.
---
apiVersion: "cilium.io/v2alpha1"
kind: CiliumL2AnnouncementPolicy
metadata:
  name: l2-announcement-policy
spec:
  serviceSelector: {}
  nodeSelector: {}
  # On a multi-node cluster, you may not want the control-plane nodes
  # making arp announcements. Uncomment the nodeSelector stanza here
  # to disable that.
  # nodeSelector:
  #   matchExpressions:
  #     - key: node-role.kubernetes.io/control-plane
  #       operator: DoesNotExist
  externalIPs: true
  loadBalancerIPs: true
  # Different hardware will show different network device names.
  # This list of regexes (in Golang format) will find all the common
  # naming schemes I've seen for network devices so that Cilium can
  # find a network interface to make arp announcements.
  interfaces:
    - ^eth+
    - ^enp+
    - ^ens+
    - ^wlan+
    - ^vmbr+
    - ^wlp+
Create a deployment and service in the playground
Talos is focused on giving you a default secure cluster out of the box, so you can’t just use kubectl create deployment hello-server --image=gcr.io/google-samples/hello-app:1.0 - talos requires you to configure the securityContext. Here’s an example deployment for nginx that runs as a non-root user and specifies the pod’s resource requirements to satisfy the Pod Security Admission configuration that ships with talos. More info about that here.

# 03-playground-nginx.yaml
apiVersion: v1
kind: Service
metadata:
  name: playground-nginx-service
  namespace: playground
  annotations:
    # Tells Cilium to manage this IP via LB IPAM
    cilium.io/lb-ipam-pool-name: "default-pool"
    # Optional: For L2/BGP to announce this IP
    cilium.io/assign-internal-ip: "true" # Or use externalIPs:
    # If using externalIPs:
    # kubernetes.io/ingress.class: "cilium" # For Ingress
    # For a specific IP
    # lbipam.cilium.io/ips: "192.168.1.50" # The specific IP you want Cilium to answer on
spec:
  type: LoadBalancer
  selector:
    app: playground-nginx-pod
  ports:
    - name: http
      port: 80
      targetPort: 8080
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: playground-nginx-app
  namespace: playground
spec:
  selector:
    matchLabels:
      app: playground-nginx-pod  # <-- must match pod labels exactly
  replicas: 1
  template:
    metadata:
      labels:
        app: playground-nginx-pod
    spec:
      # Talos is very security oriented, so we have to set up the
      # security context explicitly
      # ---------- Pod‑level security settings ----------
      securityContext:
        runAsNonRoot: true
        runAsUser: 101 # non‑root UID that the image can run as
        seccompProfile:
          type: RuntimeDefault
        # Uncomment if you need a shared FS group for volume writes
        # fsGroup: 101
      # ---------- Containers ----------
      containers:
        - name: nginx-playground-container
          image: nginxinc/nginx-unprivileged:latest # Alpine, but we force a non‑root UID
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
          # talos requires us to specify our resources instead of
          # letting k8s YOLO them
          resources:
            requests:
              memory: "64Mi"
              cpu: "250m"
            limits:
              memory: "128Mi"
              cpu: "500m"
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
Deploy the playground
If you pass a directory name to kubectl with -f, it will apply (or delete) all resources found in the .yaml files in that directory.

kubectl apply -f playground
See what IP the playground is using
It will almost certainly be the first IP address in your IP Pool, but confirm that.

kubectl get service -n playground
You’ll see something like:

NAME                       TYPE           CLUSTER-IP     EXTERNAL-IP   PORT(S)        AGE
playground-nginx-service   LoadBalancer   10.111.180.4   10.0.1.160    80:30597/TCP   1m15s
Confirm Connectivity
curl http://THE_EXTERNAL_IP
You should see the nginx default page! Don’t delete the playground yet, we’re going to use it to confirm that the Cilium Gateway API is working.

Test Cilium’s Gateway API
We configured Cilium to provide Gateway API services to the cluster when we installed it. Let’s confirm that it’s working correctly.

Make a new gateway-tests directory.

Create a Gateway
Create gateway-tests/01-create-gateway.yaml. For ease of testing we’re going to configure the gateway to allow it to be used by services in any namespace. We’re also assigning it a specific IP address so we can give it a stable FQDN. We don’t want that changing.

apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: playground-gateway
spec:
  gatewayClassName: cilium
  addresses:
    - type: IPAddress
      value: 10.0.1.160
  listeners:
  - name: http
    protocol: HTTP # Case matters!
    port: 80
    allowedRoutes:
      namespaces:
        from: All
Update the playground-nginx-service
Before we can add a HTTPRoute, we’re going to need to update the playground-nginx-service so it isn’t a LoadBalancer, so create gateway-tests/02-playground-service.yaml with the following contents:

apiVersion: v1
kind: Service
metadata:
  name: playground-nginx-service
  namespace: playground
spec:
  selector:
    app: playground-nginx-pod
  ports:
    - name: http
      port: 80 # This is what the service is listening on, and what will be routed to
      targetPort: 8080 # Port the pods are listening on, don't route directly here!
Create a HTTPRoute
Create gateway-tests/03-http-route.yaml to route all incoming requests for ip-160.mydomain.com to our playground-nginx-service.

apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: playground-http-route
  namespace: playground
spec:
  parentRefs:
  - name: playground-gateway
    namespace: default
  hostnames:
  - "ip-160.mydomain.com"
  rules:
  - backendRefs:
    - name: playground-nginx-service
      port: 80
Create the Gateway test resources
kubectl apply -f gateway-tests
Confirm it worked
curl http://ip-160.mydomain.com
It should display a “Welcome to nginx!” document that looks like this:

<!DOCTYPE html>
<html>
<head>
<title>Welcome to nginx!</title>
<style>
html { color-scheme: light dark; }
body { width: 35em; margin: 0 auto;
font-family: Tahoma, Verdana, Arial, sans-serif; }
</style>
</head>
<body>
<h1>Welcome to nginx!</h1>
<p>If you see this page, the nginx web server is successfully installed and
working. Further configuration is required.</p>

<p>For online documentation and support please refer to
<a href="http://nginx.org/">nginx.org</a>.<br/>
Commercial support is available at
<a href="http://nginx.com/">nginx.com</a>.</p>

<p><em>Thank you for using nginx.</em></p>
</body>
</html>
Congrats, you have a working talos cluster.

I cover setting up SSL by creating certificates with cert-manager, LetsEncrypt and Route 53 in Part 3 - Set up Secret Management with SOPS.

Adding a worker node
I originally planned to make that another post, but it’s only two steps.

Create another VM
The talos website recommends at least 2 CPUs and 2 GB RAM. I set mine to 16G of disk. You can use the same ISO you used when creating the control plane node.

Make sure it has a static IP assignment in DHCP.

Add it to the cluster
Create a patch file with the node name you want

# worker-1-patch.yaml
machine:
  network:
    hostname: clustername-worker-1
When the worker node console gets to Maintenance, you can add it with a one line talosctl command

talosctl apply-config --insecure --nodes "$WORKER_IP" --file worker.yaml --config-patch @worker-1-patch.yaml
My proxmox cluster isn’t on beefy hardware so it took a couple of minutes for the new node to join the cluster and start accepting workload.

Problems I ran into
When I was making this post, I ran into a couple of problems because I was redoing everything to run on a single node blog cluster and made some mistakes tidying things up for a post.

curl fails to connect
While testing the LoadBalancer service, even though the service LoadBalancer shows that it has an external IP, when you test with curl, it gives an error message similar to this:

$ curl http://10.0.1.160/
curl: (7) Failed to connect to 10.0.1.160 port 80 after 16 ms: Could not connect to server
And when you check the pods

kubectl get pods -n playground
it shows the worker pod as pending, not crash loop backoff, not creating, just pending.

NAMESPACE     NAME                                          READY   STATUS    RESTARTS      AGE
playground    pod/playground-nginx-app-6d7ddb5b95-lv82x     0/1     Pending   0             12s
When I ran into this with the a blog cluster while writing this post, it was because I made the test cluster a single node cluster and forgot to set allowSchedulingOnControlPlanes to true, so there was no place to schedule the pods. You can fix this by applying an updated configuration.

talosctl apply-config --insecure \
  --nodes $(CONTROL_PLANE_IP) \
  --file controlplane.yaml \
  --config-patch @controlplane-1-patch.yaml
curl connects, but you get a 404
While testing the gateway, curl connects to the IP but you get a 404 error.

curl -iv http://ip-160.mydomain.com/index.html
* Host ip-160.mydomain.com:80 was resolved.
* IPv6: (none)
* IPv4: 10.0.1.160
*   Trying 10.0.1.160:80...
* Established connection to ip-160.mydomain.com (10.0.1.160 port 80) from 10.0.1.121 port 61150
* using HTTP/1.x
> GET /index.html HTTP/1.1
> Host: ip-160.mydomain.com
> User-Agent: curl/8.17.0
> Accept: */*
>
* Request completely sent off
< HTTP/1.1 404 Not Found
< date: Sun, 04 Jan 2026 00:36:07 GMT
< server: envoy
< content-length: 0
<
* Connection #0 to host ip-160.mydomain.com:80 left intact
I ran into this during testing because I forgot to update the gateway yaml file to allow all namespaces after I moved all the test manifests into the playground namespace.

Talos reboots so fast that when I make settings changes to a single node cluster I always reboot the control plane node with talosctl reboot -n $CONTROL_PLANE_IP.

You changed cilium settings but they don’t appear to have any affect
Some changes to cilium settings require you to restart cilium pods to pick them up.

kubectl -n kube-system rollout restart ds/cilium
kubectl -n kube-system rollout restart ds/cilium-envoy
kubectl -n kube-system rollout restart deployment/cilium-operator
Tips
If you plan on standing up and tearing down VMs, copy the MAC of the first one. Go to the proxmox datacenter UI, select the VM, then select Hardware and double click Network Device for details) and set each replacement to that MAC. Your DHCP server uses a machine’s MAC to determine if it should get a static assignment, so recycling the MAC keeps you from having to update DHCP each time you bring up a new VM.

This is one of the few times it’s a good idea to reuse a MAC - having two VMs or physical machines with the same MAC running simultaneously will cause problems with on your network.