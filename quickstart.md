## How to create a fork of ifs‑source on ECMWF Bitbucket

Starting at the [DE ifs‑source repo](https://git.ecmwf.int/projects/DE/repos/ifs-source/browse) on Bitbucket:

1. Click the **Fork** icon on the left-side bar
   ![Fork Icon](https://github.com/user-attachments/assets/80df2de6-3be4-4fd6-9c20-296027fda92c)  
   (or go directly to the [fork creation page](https://git.ecmwf.int/projects/DE/repos/ifs-source?fork))
2. Accept the default location (your personal project space).
3. Set **Repository name** to something appropriate, for instance `ifs-source-compare-example`.
4. Un‑check **Enable fork syncing**.

## How to create a feature branch on your ifs-source fork

Starting at the browse page of your newly created fork (https://git.ecmwf.int/users/ecme####/repos/ifs-source-compare-example/browse, where ecme#### is your Bitbucket username):

1. Click on the **Create branch** icon on the left-side bar <img width="23" height="28" alt="image" src="https://github.com/user-attachments/assets/57db7f4c-d288-48e5-a50c-9075bee63fc3" />
2. Create a branch as desired. For example, create a feature branch by selecting **Branch type > Feature**.
3. Choose an appropriate name. For example, `ifsnemo-compare-test`.
4. Click the **Create branch** button.
<img width="585" height="386" alt="Screenshot_20250724_133502" src="https://github.com/user-attachments/assets/7adcbd68-4746-4ed7-9b01-db7798f257c1" />

---

aliases:

* “ifsnemo‑build branch testing”
  tags:
* ifsnemo
* tutorial
* overrides

## How to instruct **ifsnemo‑build** to test your branch

Having made the modifications in your branch, on your local machine create an `overrides.yaml` file with the following contents:

```yaml
---
environment:
  - export DNB_IFSNEMO_URL="https://git.ecmwf.int/scm/~ecme####"
  - export IFS_BUNDLE_IFS_SOURCE_GIT="$DNB_IFSNEMO_URL/ifs-source-compare-example.git"
  - export IFS_BUNDLE_IFS_SOURCE_VERSION="feature/ifsnemo-compare-test"
  - export DNB_SANDBOX_SUBDIR="ifsFORKEX.SP.CPU.GPP"
```

* Replace `ecme####` with your own username.
* Choose `DNB_SANDBOX_SUBDIR` as you see fit.

From this point, repeat the steps in the [testing quickstart guide](./quickstart-testing.md) starting after **Step 1.3: Configure and Clone ifsnemo‑build**.
