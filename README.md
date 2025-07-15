# ifsnemo-compare

Prerequisites:
ifsnemo-build, located at https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build
  The complete set of instructions are given in the ifsnemo-build setup instructions here: https://hackmd.io/@mxKVWCKbQd6NvRm0h72YpQ/SkHOb6FZgg build IFS-NEMO using ifsnemo-build
  but an abridged set of instructions for setup on MN5-GPP follow.
1. ON YOUR LOCAL MACHINE
   a. Download the `yq` YAML processing tool to `~/bin`
   `mkdir ~/bin`
   `wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O ~/bin/yq`
   and add `~/bin` to PATH:
   To `~/.bashrc` add the line
   `export PATH="~/bin:$PATH"`

   b. To permit access to the `generic-hpc-scripts` submodule of `ifsnemo-build` Create a `~/.netrc` file containing the entry
   ```
   machine earth.bsc.es
   login XXXXXXX
   password YYYYYYYYYYYYYYYYY
   ```
   where your @username in earth.bsc.es is the login name XXXXXXX
   and YYYYYYYYYYYYYYYYY is a personal access token which may be created under the "Personal Access Token" heading in the following page: https://earth.bsc.es/gitlab/-/profile/personal_access_tokens
   Note!
   remove the expiration date and select all checkboxes under the "Select scopes" sub-heading when creating the token

   c. Clone ifsnemo-build, recursively!, with
   `git clone --recursive https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build.git`
   in the `ifsnemo-build` directory, set the `machine.yaml` to the generic machine file `dnb-generic.yaml`
   `ln -s dnb-generic.yaml machine.yaml`
   and within `ifsnemo-build`,
   create two files:
   1. `overrides.yaml` containing
      ```
      ---
      environment:
        - export DNB_SANDBOX_SUBDIR="ifsMASTER.SP.CPU.GPP"
      ```
   2. `account.yaml` containing
      ```
      ---
      # MN5-GPP:
      psubmit:
        queue_name: ""
        account: bsc32
        node_type: gp_debug
      
      # MN5-ACC:
      #psubmit:
      #  queue_name: ""
      #  account: bsc32
      #  node_type: acc_debug
      
      # LUMI-G:
      #psubmit:
      #  queue_name: "standard-g"
      #  account: project_465000454
      ```

  d. Download and unpack the needed files (requires internet access!) with
  `./dnb.sh :du`

   Then, `tar` the `ifsnemo-build` directory for `scp` transfer with 
   `tar czf ../ifsnemo-build.tar.gz *`
   Use `scp` to copy the `ifsnemo-build.tar.gz` tarball onto MN5 with
   `scp ~/ifsnemo-build.tar.gz bsc<XXXXXX>@glogin4.bsc.es:/gpfs/projects/bsc32/bsc<XXXXXX>/`

   e. ON MARENOSTRUM 5 GPP
   Navigate to the `ifsnemo-build` directory `cd /gpfs/projects/bsc32/bsc<XXXXXX>/ifsnemo-build/`
   Request an interactive debug with `salloc` for building
   `salloc --qos=gp_debug --partition=standard -A ehpc01 -c 112 --nodes=1 -t 02:00:00 --exclusive`

   From the GPP compute node, Run the build command `./dnb.sh :b`

   Relinquish the compute node with Ctrl+D

   Run the install command `./dnb.sh :i` on a GPP login node

   When completed, 
   from `glogin4`, download and add the `psubmit` and `yq` utilities
   ```
   cd
   mkdir bin
   cd bin
   wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O ./yq
   git clone https://github.com/a-v-medvedev/psubmit.git
   mv psubmit/* .
   ```
   append to PATH as needed by adding the line
   ```
   PATH="$HOME/bin:$PATH"
   ```
   and `source ~/.bashrc` to take the changes in as needed
   
   go to the `ifsnemo-build/ifsnemo` "testbed" directory and run an example with psubmit

   ```
   psubmit.sh -n 1 -u ifsMASTER.SP.CPU.GPP
   ```
If this works, introduce the `ifsnemo-compare` system by cloning from within `ifsnemo-build/ifsnemo`

