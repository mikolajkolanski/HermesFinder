{
  description = ''
    Weryfikator tez klimatycznych — backend FastAPI + frontend vanilla JS
    na danych NASA (POWER, GISTEMP, Vital Signs, NSIDC).

    - `nix run .#`            -> serwer na http://127.0.0.1:8000
    - `nix develop`           -> srodowisko deweloperskie (Python + zaleznosci)
    - nixosModules.default    -> usluga systemd `services.climate-verifier`

    Klucze planera LLM (opcjonalne, bez nich dziala fallback TF-IDF):
    GEMINI_API_KEY / OPENAI_API_KEY / OPENROUTER_API_KEY, ewentualnie
    LLM_PROVIDER, LLM_TIMEOUT, CV_CACHE_TTL_DAYS. Katalogi robocze:
    CV_CACHE_DIR, CV_INDEX_PATH (domyslnie ~/.local/state/climate-verifier).
  '';

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;

      envFor = system: rec {
        pkgs = nixpkgs.legacyPackages.${system};
        pythonEnv = pkgs.python312.withPackages (ps: with ps; [
          fastapi
          pydantic
          uvicorn
          httpx
          numpy
          scipy
        ]);
      };

      package = system:
        let
          e = envFor system;
          inherit (e) pkgs pythonEnv;
        in
        pkgs.stdenvNoCC.mkDerivation {
          pname = "climate-verifier";
          version = "3.0.1";

          src = pkgs.lib.cleanSource ./.;

          dontConfigure = true;
          dontBuild = true;

          installPhase = ''
            runHook preInstall

            share=$out/share/climate-verifier
            mkdir -p "$share" $out/bin
            cp -r backend frontend "$share/"
            chmod -R u+w "$share"
            rm -rf "$share/backend/data/cache"

            # Wrapper: katalog stanu poza read-only /nix/store oraz
            # konfigurowalny host/port (CV_HOST, CV_PORT).
            cat > $out/bin/climate-verifier <<'WRAPPER'
            #!${pkgs.runtimeShell}
            # Weryfikator tez klimatycznych (dane NASA).
            # Klucze LLM: GEMINI_API_KEY / OPENAI_API_KEY / OPENROUTER_API_KEY
            # (+ opcjonalnie LLM_PROVIDER, LLM_TIMEOUT, CV_CACHE_TTL_DAYS).
            state="''${XDG_STATE_HOME:-$HOME/.local/state}/climate-verifier"
            export CV_CACHE_DIR="''${CV_CACHE_DIR:-$state/cache}"
            export CV_INDEX_PATH="''${CV_INDEX_PATH:-$state/index.json}"
            exec ${pythonEnv}/bin/python -m uvicorn main:app \
              --host "''${CV_HOST:-127.0.0.1}" \
              --port "''${CV_PORT:-8000}" \
              --app-dir @APPDIR@/backend
            WRAPPER
            sed -i "s|@APPDIR@|$share|" $out/bin/climate-verifier
            chmod +x $out/bin/climate-verifier

            runHook postInstall
          '';

          meta = with pkgs.lib; {
            description = "Weryfikator tez klimatycznych — dashboard danych NASA";
            mainProgram = "climate-verifier";
            platforms = platforms.unix;
          };
        };
    in
    {
      packages = forAllSystems (system: rec {
        climate-verifier = package system;
        default = climate-verifier;
      });

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/climate-verifier";
        };
      });

      devShells = forAllSystems (system:
        let e = envFor system; in {
          default = e.pkgs.mkShellNoCC {
            packages = [ e.pythonEnv ];
            shellHook = ''
              cd backend 2>/dev/null || true
              echo 'Weryfikator tez klimatycznych — dev shell (backend).'
              echo 'Start serwera: python -m uvicorn main:app --port 8000'
            '';
          };
        });

      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.services.climate-verifier;
          pkg = self.packages.${pkgs.system}.default;
        in
        {
          options.services.climate-verifier = {
            enable = lib.mkEnableOption ''
              weryfikatora tez klimatycznych — dashboard danych NASA
              (backend FastAPI, domyslnie http://127.0.0.1:8000)
            '';
            host = lib.mkOption {
              type = lib.types.str;
              default = "127.0.0.1";
              description = "Adres nasluchiwania backendu.";
            };
            port = lib.mkOption {
              type = lib.types.port;
              default = 8000;
              description = "Port nasluchiwania backendu.";
            };
            environmentFile = lib.mkOption {
              type = lib.types.nullOr lib.types.path;
              default = null;
              example = "/run/secrets/climate-verifier.env";
              description = ''
                Plik doklejany jako EnvironmentFile — klucze planera LLM
                (GEMINI_API_KEY / OPENAI_API_KEY / OPENROUTER_API_KEY,
                opcjonalnie LLM_PROVIDER, LLM_TIMEOUT, CV_CACHE_TTL_DAYS).
                Nie trzymaj sekretow w plikach konfiguracyjnych.
              '';
            };
          };

          config = lib.mkIf cfg.enable {
            systemd.services.climate-verifier = {
              description = "Weryfikator tez klimatycznych — dane NASA";
              wantedBy = [ "multi-user.target" ];
              wants = [ "network-online.target" ];
              after = [ "network-online.target" ];

              environment = {
                CV_HOST = cfg.host;
                CV_PORT = toString cfg.port;
                CV_CACHE_DIR = "/var/lib/climate-verifier/cache";
                CV_INDEX_PATH = "/var/lib/climate-verifier/index.json";
              };

              serviceConfig = {
                ExecStart = "${pkg}/bin/climate-verifier";
                DynamicUser = true;
                StateDirectory = "climate-verifier";
                EnvironmentFile = lib.mkIf
                  (cfg.environmentFile != null) cfg.environmentFile;
                Restart = "on-failure";
                RestartSec = 5;
                # utwardzenie
                NoNewPrivileges = true;
                PrivateTmp = true;
                ProtectSystem = "strict";
                ProtectHome = true;
              };
            };
          };
        };
    };
}
