# Azure Deployment Plan

> **Status:** Deployed (partial — see Known Limitations)

Generated: 2026-09-11


---

## 1. Project Overview

**Goal:** Host the `camcontrol` gateway (`camera_bridge`, FastAPI + ffmpeg + paramiko/SSH)
as an always-on Azure App Service (Linux container) instance, so cameras 246/252
(currently polled by a gateway that only runs when this dev laptop is on) keep
collecting continuously, and so the 3rd-party RTSP camera can be reached too.
Provide the router/DDNS/config/app-profile data needed on the camera + phone
side to point at the new cloud gateway.

**Path:** Add Components (existing local-only app gains a cloud hosting target;
the local gateway/app code is unchanged, only reachable-over-internet camera
addressing changes).

---

## 2. Requirements

| Attribute | Value |
|-----------|-------|
| Classification | Development (personal/home use, single instance, no HA requirement) |
| Scale | Small (1 gateway instance, 3 cameras) |
| Budget | Cost-optimized (B1 Basic App Service Plan) |
| **Subscription** | wolffofficesub (3ec4f525-3849-4d69-93ef-c52b426f197c), tenant `wolff` |
| **Location** | eastus2 (matches existing `wolffoffcompute` RG; region choice does not affect camera reachability, which is over the public internet) |

---

## 3. Components Detected

| Component | Type | Technology | Path |
|-----------|------|------------|------|
| camera_bridge gateway | API (FastAPI + background pollers) | Python 3.12, uvicorn, paramiko (SSH), ffmpeg (subprocess), pydantic | `src/camera_bridge/` |
| CamControl app | Mobile client (not deployed to Azure) | Flutter/Android | `ui/` |
| Camera config | Runtime data, currently local file, gitignored | JSON (`host`, `port`, `username`, `password` per camera) | `config/cameras.json` |
| Captures | Runtime data (snapshots/recordings) | Local disk today (`./captures`); app already supports Azure Blob via `AzureBlobStorageConfig` | `captures/` |

---

## 4. Recipe Selection

**Selected:** AZCLI (direct `az` commands, no azd/Bicep wrapper)

**Rationale:**
- Single small resource set (1 App Service plan, 1 Web App, 1 storage account),
  reusing 2 already-existing resources (ACR `wolffacr`, Key Vault
  `wolffofficekvkv2`) in this subscription — a full azd/Bicep environment adds
  overhead with little reproducibility benefit for a single personal instance.
- User explicitly chose App Service (Linux container), not Container Apps.
- No existing `azure.yaml`/Bicep in this repo to extend.

---

## 5. Architecture

**Stack:** App Service (Linux, custom container)

### Service Mapping

| Component | Azure Service | SKU |
|-----------|---------------|-----|
| camera_bridge gateway | App Service (Linux, Web App for Containers) | B1 Basic, Always On |
| Container image | Azure Container Registry | **Reuse existing** `wolffacr` (new repo `camcontrol-gateway`) |
| Persistent config (`cameras.json`, `users.json`) | Storage Account → Azure Files share, mounted at `/home/config` | Standard_LRS |
| Captures (snapshots/recordings) | Storage Account → Blob container `captures` (via app's existing `azure_blob` storage provider + Managed Identity, no key) | Same storage account, Standard_LRS |
| Admin API key + secrets | **Reuse existing** Key Vault `wolffofficekvkv2` (access-policy vault, not RBAC) | — |

### Supporting Services

| Service | Purpose |
|---------|---------|
| System-assigned Managed Identity (Web App) | AcrPull on `wolffacr`; Storage Blob Data Contributor on new storage account; Key Vault access policy (get secrets) on `wolffofficekvkv2` |
| Key Vault reference (`API_KEY` app setting) | Required admin-API auth — currently **unset locally**, which leaves `/api/config` etc. unauthenticated; MUST be set before internet exposure |
| HTTPS Only | Enforced on the Web App (default) |

### Security notes (must resolve before/at deploy)

1. **Camera SSH password is currently blank** (`config/cameras.json`: `"password": ""` for both `10.0.0.246` and `10.0.0.252`). You confirmed you'll set a strong password on both cameras — this **must** happen before (or at the same time as) the router port-forward goes live, since a blank-password root SSH server directly on the internet is trivially compromised.
2. Router port-forwards expose the cameras' SSH (and RTSP, for the 3rd-party camera) to the **entire internet**, not just Azure — recommend forwarding non-default external ports (e.g. `22246→10.0.0.246:22`, `22252→10.0.0.252:22`) to cut down automated scanner noise, and re-checking camera firmware for any available brute-force lockout setting.
3. `API_KEY` will be generated and stored as a Key Vault secret, referenced by the Web App (never baked into the image or committed).

---

## 6. Provisioning Limit Checklist

### Phase 1: Resource Inventory

| Resource Type | Number to Deploy | Total After Deployment | Limit/Quota | Notes |
|---------------|------------------|------------------------|--------------|-------|
| Microsoft.Web/serverfarms (B1, eastus2) | 1 | 1 | 100 per region/subscription (default, Basic tier) | Fetched from: Azure Resource Graph (0 existing in eastus2) + [service limits docs](https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#app-service-limits) |
| Microsoft.Web/sites (Web App) | 1 | 1 | Bound by App Service Plan capacity, not a separate hard cap | Fetched from: Azure Resource Graph |
| Microsoft.Storage/storageAccounts (eastus2) | 1 | 2 | 250 per region/subscription (default) | Fetched from: Azure Resource Graph (1 existing: `wolffoffcomputediag`) + [service limits docs](https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#storage-limits) |
| Microsoft.ContainerRegistry/registries | 0 (reusing `wolffacr`) | n/a | n/a | No new registry |
| Microsoft.KeyVault/vaults | 0 (reusing `wolffofficekvkv2`) | n/a | n/a | No new vault |

**Status:** ✅ All resources within limits (single Basic-tier App Service Plan and one new Storage Account, far below default subscription quotas; no compute-VM-family quota consumed since this is PaaS, not IaaS).

---

## 7. Execution Checklist

### Phase 1: Planning
- [x] Analyze workspace
- [x] Gather requirements
- [x] Confirm subscription and location with user (`wolffofficesub`)
- [x] Prepare resource inventory
- [x] Fetch quotas and validate capacity (Resource Graph counts + documented defaults; single small PaaS deployment)
- [x] Scan codebase
- [x] Select recipe (AZCLI)
- [x] Plan architecture
- [x] **User approved this plan** ("i want the azure gateway")

### Phase 2: Execution
- [x] Create resource group `rg-camcontrol` (eastus2)
- [x] Create storage account `stcamcontrolwolff` (eastus2) + Azure Files share `config` (ARM-created; **not mountable** -- see limitations) + Blob container `captures` (ARM-created)
- [x] Write `Dockerfile` for `camera_bridge` (Python 3.12-slim + ffmpeg + package install)
- [x] Build & push image to `wolffacr/camcontrol-gateway:latest` (via `az acr build`, westus)
- [x] Create App Service Plan `asp-camcontrol` (Linux, B1) -- **westus2**, not eastus2: subscription had 0 B1 VM quota in eastus2, available in westus2
- [x] Create Web App `camcontrol-wolff` (`https://camcontrol-wolff.azurewebsites.net`) with container config, `WEBSITES_PORT=8000`
- [x] Enable system-assigned Managed Identity (`31c9fe7a-2a2b-43f6-87d9-ab0c2e65d18f`)
- [x] ACR pull: working via registry admin credentials (`adminUserEnabled=true` on `wolffacr`, auto-wired by `az webapp create`) -- **not** managed identity (see limitations)
- [x] Generate `API_KEY` -- stored as a plain App Service setting (**not** Key Vault-backed, see limitations)
- [ ] ~~Mount Azure Files share~~ -- blocked, see limitations
- [x] Set `WEBSITES_PORT`, `API_KEY` app settings
- [x] Functional verification: `/api/health` returns `{"status":"ok","cameras":0}`
- [ ] Produce device-side config: router port-forward table, DDNS setup, updated `cameras.json`, phone app Gateway URL + API key -- pending user follow-up

### Known Limitations (blocked by tenant security posture, not code)
1. **No persistent camera config yet.** `stcamcontrolwolff` has `allowSharedKeyAccess=false` (tenant security baseline) -- App Service's native Azure Files mount requires the storage account key and cannot work while shared-key access is disabled. Blob-based sync was added in code (`blob_config_sync.py`, gated by `CONFIG_BLOB_ACCOUNT_URL`/`CONFIG_BLOB_CONTAINER` env vars, uses Azure AD only) as the policy-compliant alternative, but wiring it up requires a **Storage Blob Data Contributor** role assignment, which is currently blocked (see #2). Until resolved, cameras added via the app's Settings UI will be **lost on container restart/redeploy**.
2. **RBAC role-assignment writes are blocked.** `az role assignment create` (AcrPull on `wolffacr`, Storage Blob Data Contributor on `stcamcontrolwolff`) failed with `AuthorizationFailed ... ABAC condition that is not fulfilled` for `geraldwolff@wolffentp.org`. This is a tenant-enforced Attribute-Based Access Control restriction on `Microsoft.Authorization/roleAssignments/write` -- did not attempt to bypass it. AcrPull isn't blocking (registry admin credentials cover it); Storage Blob Data Contributor still needed for #1.
3. **Key Vault secret writes cross-tenant issuer mismatch.** `az keyvault secret set` on `wolffofficekvkv2` failed: `AKV10032: Invalid issuer` -- the vault's expected token issuers (tenants `653eac6f...`, `f8cdef31...`, `e2d54eb5...`) don't include the subscription's own tenant (`e594a530...`, "wolff") that the CLI session authenticates against for this subscription. Setting a Key Vault **access policy** for the identity succeeded (control-plane, ARM), but writing the actual secret value (data-plane) did not. `API_KEY` was set as a plain App Service application setting instead (still encrypted at rest by the platform, just not KV-managed).

### Phase 3: Validation
- [ ] Invoke azure-validate skill (or manual verification given AZCLI recipe) before going live

### Phase 4: Deployment
- [x] Deploy container, verify `/api/health`
- [ ] Verify camera connectivity from the cloud instance (pending router port-forward + camera password hardening on the user's side)

---

## 8. Files to Generate

| File | Purpose | Status |
|------|---------|--------|
| `.azure/deployment-plan.md` | This plan | ✅ |
| `Dockerfile` | Container build for `camera_bridge` (Python 3.12-slim + ffmpeg) | ⏳ |
| `.dockerignore` | Keep secrets/venv/captures out of the build context | ⏳ |

---

## 9. Next Steps

> Current: Awaiting user approval of this plan

1. User confirms/adjusts the plan (naming, region, whether to reuse `wolffacr`/`wolffofficekvkv2`, router port choices).
2. Generate Dockerfile, provision resources via `az` CLI, deploy, and hand back router/DDNS/app config.
