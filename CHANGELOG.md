# Changelog

## [0.5.0](https://github.com/darren-iac/action-cletus-code/compare/v0.4.0...v0.5.0) (2026-01-05)


### Features

* add multi-skill support with JSON array format ([#12](https://github.com/darren-iac/action-cletus-code/issues/12)) ([b0aa3b8](https://github.com/darren-iac/action-cletus-code/commit/b0aa3b8af955292d5505277fdc8d4c882c967b31))


### Bug Fixes

* ensure only one bot comment per PR review cycle ([dc4715b](https://github.com/darren-iac/action-cletus-code/commit/dc4715b01a2f356d1676ded45100fd2ab68ee00b))
* pass json-schema inline instead of file path ([ae6fe86](https://github.com/darren-iac/action-cletus-code/commit/ae6fe864a510f718f3ba9a914dd3e76ca99b98f7))
* pass structured output via env var to avoid parsing issues ([94f7efa](https://github.com/darren-iac/action-cletus-code/commit/94f7efa7575197f780b8ebd64d3ea1c673f24da6))
* prevent review-workflows.yml from failing on push events ([cfd4f8c](https://github.com/darren-iac/action-cletus-code/commit/cfd4f8c8c3b0eff0cff0f78821f24c7af65291d6))
* quote skills JSON array arguments ([a5b29aa](https://github.com/darren-iac/action-cletus-code/commit/a5b29aa6d186f501dbc0b828bfa1ec2da3a37d6e))
* use env var for structured output to avoid YAML parsing issues ([aa91da5](https://github.com/darren-iac/action-cletus-code/commit/aa91da5bed6e577bfc482e05a269aa8caea12bb5))
* use heredoc to safely write JSON output ([24123e5](https://github.com/darren-iac/action-cletus-code/commit/24123e543aa05687d2c8882fc599ee78e255a220))
* use PowerShell to write JSON with special characters ([52be9ef](https://github.com/darren-iac/action-cletus-code/commit/52be9efd364adbffa686e741df4207869dc03f7a))
* use printf instead of echo for JSON output ([55b1a10](https://github.com/darren-iac/action-cletus-code/commit/55b1a10a274e7746b657274c71d27ecdfc461e54))
* use review-schema.json from output directory ([e4422a8](https://github.com/darren-iac/action-cletus-code/commit/e4422a8cfaa834c431d7b7991d36ee8edd4838c7))
* use skills-json input instead of deprecated skills ([6f8be6d](https://github.com/darren-iac/action-cletus-code/commit/6f8be6dbe7d14dbf20a74194b7270b654824f505))
* use structured output to guarantee review.json creation ([950dab6](https://github.com/darren-iac/action-cletus-code/commit/950dab680ed5fb0275473d64737a17c6167dd0ce))


### Documentation

* update action description to mention structured output ([c21fa22](https://github.com/darren-iac/action-cletus-code/commit/c21fa22d38c14f05ee1a92b15beef721421db39e))
* update README for internal use ([77c42a8](https://github.com/darren-iac/action-cletus-code/commit/77c42a82bd4d238336e8c17f8b56e84d1f3cdd36))

## [0.4.0](https://github.com/darren-iac/action-cletus-code/compare/v0.3.1...v0.4.0) (2026-01-05)


### Features

* add local act testing support with Colima ([a3b42d0](https://github.com/darren-iac/action-cletus-code/commit/a3b42d0765a909e99a09c80a8066c8d920c4933a))
* **ci:** add act integration tests and workflow caching ([f16b391](https://github.com/darren-iac/action-cletus-code/commit/f16b391c8d7071a949d9058e22600da67e39e548))

## [0.3.1](https://github.com/darren-iac/action-cletus-code/compare/v0.3.0...v0.3.1) (2026-01-04)


### Bug Fixes

* copy review.json from workspace to action directory ([20bb327](https://github.com/darren-iac/action-cletus-code/commit/20bb327302b8f5a356c92301e9d0d560f53eabb3))

## [0.3.0](https://github.com/darren-iac/action-cletus-code/compare/v0.2.6...v0.3.0) (2026-01-04)


### Features

* accept space-separated changed-files input in Python ([1380599](https://github.com/darren-iac/action-cletus-code/commit/1380599aafdcb712f383959abd74e1469a2d7501))

## [0.2.6](https://github.com/darren-iac/action-cletus-code/compare/v0.2.5...v0.2.6) (2026-01-04)


### Bug Fixes

* correct imports in process_review.py ([48d5364](https://github.com/darren-iac/action-cletus-code/commit/48d5364295ca169d14b948a8e8b41528adc04b2f))

## [0.2.5](https://github.com/darren-iac/action-cletus-code/compare/v0.2.4...v0.2.5) (2026-01-04)


### Bug Fixes

* use single quotes for changed-files to preserve JSON ([ea324d0](https://github.com/darren-iac/action-cletus-code/commit/ea324d040adfda4d9cfb019d427e9d99bab801b0))

## [0.2.4](https://github.com/darren-iac/action-cletus-code/compare/v0.2.3...v0.2.4) (2026-01-04)


### Bug Fixes

* use correct .local/bin path for uv ([426a905](https://github.com/darren-iac/action-cletus-code/commit/426a905c87b47ac107f2e430ea7a66dc24287d3d))

## [0.2.3](https://github.com/darren-iac/action-cletus-code/compare/v0.2.2...v0.2.3) (2026-01-04)


### Bug Fixes

* add PATH export for uv in all steps ([85616f4](https://github.com/darren-iac/action-cletus-code/commit/85616f43c5ec4ea0731a0238f078309ffef80f95))

## [0.2.2](https://github.com/darren-iac/action-cletus-code/compare/v0.2.1...v0.2.2) (2026-01-04)


### Bug Fixes

* update root action.yml with correct inputs ([84c7d6e](https://github.com/darren-iac/action-cletus-code/commit/84c7d6e8b3ae5c7183e434dd774f12ae75a4d357))

## [0.2.1](https://github.com/darren-iac/action-cletus-code/compare/v0.2.0...v0.2.1) (2026-01-04)


### Documentation

* update README for v0.3.0 with caching fix ([646ea2f](https://github.com/darren-iac/action-cletus-code/commit/646ea2fe6638529c8bd6cbd9b0318070fe3650df))

## [0.2.0](https://github.com/darren-iac/action-cletus-code/compare/v0.1.0...v0.2.0) (2026-01-04)


### Features

* add settings input for Claude Code configuration ([7cf81fe](https://github.com/darren-iac/action-cletus-code/commit/7cf81fe99d6fd5bbce275da7680137b980ad7bc6))
* publish updated action with all inputs ([84ddbb3](https://github.com/darren-iac/action-cletus-code/commit/84ddbb381a5c323bb8b846e4bc89070af29a52b1))

## 0.1.0 (2026-01-04)


### Features

* implement plugin system, skills, and comprehensive testing ([3cff02d](https://github.com/darren-iac/action-cletus-code/commit/3cff02dce4d54e5875af01d51b3d8df36c45c707))
* reorganize as GitHub Action with proper structure ([86a5328](https://github.com/darren-iac/action-cletus-code/commit/86a532888590e860ce777fae377509d8029e713e))


### Bug Fixes

* add process_review module at repo root for workflow compatibility ([5bea769](https://github.com/darren-iac/action-cletus-code/commit/5bea7690a4a79fa566b285cd9f1f16f88d217494))
* use official release-please action ([d8fb243](https://github.com/darren-iac/action-cletus-code/commit/d8fb24313909afbcffc8ff309bab4b35eef7d136))
