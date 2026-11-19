{
  description = "claude-dot-bak: scheduled backups of Claude Code, Claude Desktop and claude.ai exports";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems f;
      perSystem = system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        py = pkgs.python3;

        # Playwright from nixpkgs ships browsers that match its driver version,
        # so nothing gets downloaded at runtime.
        playwrightEnv = {
          PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
          PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
        };

        claude-bak = py.pkgs.buildPythonApplication {
          pname = "cli-anything-claude-bak";
          version = "0.1.0";
          src = ./agent-harness;
          pyproject = true;
          build-system = [ py.pkgs.setuptools ];
          dependencies = [ py.pkgs.click py.pkgs.playwright ];
          nativeCheckInputs = [ py.pkgs.pytestCheckHook ];
          # Browser tests need a writable home; the rest run in the sandbox.
          preCheck = ''export HOME=$TMPDIR'';
          disabledTestPaths = [ "cli_anything/claude_bak/tests/test_autoexport.py" ];
          makeWrapperArgs = pkgs.lib.concatLists (pkgs.lib.mapAttrsToList
            (k: v: [ "--set-default" k v ]) playwrightEnv);
          meta.mainProgram = "cli-anything-claude-bak";
        };
      in
      {
        packages.default = claude-bak;
        packages.claude-bak = claude-bak;

        apps.default = {
          type = "app";
          program = "${claude-bak}/bin/cli-anything-claude-bak";
        };

        devShells.default = pkgs.mkShell ({
          packages = [
            (py.withPackages (ps: [ ps.click ps.playwright ps.pytest ps.setuptools ]))
            pkgs.git
          ];
          shellHook = ''
            export PYTHONPATH="$PWD/agent-harness''${PYTHONPATH:+:$PYTHONPATH}"
            # Run the CLI straight from the working tree.
            mkdir -p .direnv/bin
            cat > .direnv/bin/cli-anything-claude-bak <<EOF
            #!/usr/bin/env bash
            exec python -m cli_anything.claude_bak "\$@"
            EOF
            chmod +x .direnv/bin/cli-anything-claude-bak
            export PATH="$PWD/.direnv/bin:$PATH"
          '';
        } // playwrightEnv);

        checks.default = claude-bak;
      };
      all = forAll perSystem;
    in
    {
      packages = forAll (s: all.${s}.packages);
      apps = forAll (s: all.${s}.apps);
      devShells = forAll (s: all.${s}.devShells);
      checks = forAll (s: all.${s}.checks);
    };
}
