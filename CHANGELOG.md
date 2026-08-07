# Changelog

## [0.9.0](https://github.com/chio-labs/streambuild/compare/v0.8.0...v0.9.0) (2026-08-07)


### Features

* improve CLI plan and error presentation ([74d1b62](https://github.com/chio-labs/streambuild/commit/74d1b6265c5eaf0dbe23f562e204c1679d7aa952))
* improve CLI plan and error presentation ([863c744](https://github.com/chio-labs/streambuild/commit/863c744b420c8392f27da57e3a4828a9539798e8))


### Bug Fixes

* package dev UI assets in distributions ([1cb9a84](https://github.com/chio-labs/streambuild/commit/1cb9a84576f6633edcd21a513334b619ef8a651a))
* package dev UI assets in distributions ([96b2976](https://github.com/chio-labs/streambuild/commit/96b2976a3f29ce111267ca568076fdca1f191bbd))

## [0.8.0](https://github.com/chio-labs/streambuild/compare/v0.7.0...v0.8.0) (2026-08-07)


### Features

* add durable UI run execution model ([3146296](https://github.com/chio-labs/streambuild/commit/314629699e3be601ffcc0702914f93bd1c4ed304))

## [0.7.0](https://github.com/chio-labs/streambuild/compare/v0.6.0...v0.7.0) (2026-08-07)


### ⚠ BREAKING CHANGES

* remove the direct-build preflight phase and retention coverage state

### Features

* --events JSONL stream and durable _streambuild_run_events timeline ([b081b7a](https://github.com/chio-labs/streambuild/commit/b081b7a4ffdd9dd7229671c84903a9e81e758927))
* add authored source freshness policies ([0a6e90a](https://github.com/chio-labs/streambuild/commit/0a6e90a9e5768e8905039178c2e6a70ca0bc20f2))
* add deployment CLI resource family ([c9abde7](https://github.com/chio-labs/streambuild/commit/c9abde75ce5d60e9337f075519c0536140a92623))
* add description to the MODEL() header ([d574e88](https://github.com/chio-labs/streambuild/commit/d574e88549b9768acd204468fbc116ca24b7e4b8))
* add stb dev ([4b2043d](https://github.com/chio-labs/streambuild/commit/4b2043dcd28e9f6665eca4de086ceb9023217ec6))
* checks history, dagster-aligned runs table, plan preload ([8e179b5](https://github.com/chio-labs/streambuild/commit/8e179b52903dadffdf8babbec4189f56c5623d00))
* dagster-style runs page, snapshot refresh, macro descriptions, and gap cleanup ([559e9d4](https://github.com/chio-labs/streambuild/commit/559e9d4085c8f8b13df7275ba3280edfeba4c053))
* declare generic audits in the MODEL() header; delete schema.yml ([efa1ef9](https://github.com/chio-labs/streambuild/commit/efa1ef94c21c1b3137ba41151471ee2e4160588f))
* dev UI - SvelteKit frontend, server-backed API client, and build glue ([e3546b2](https://github.com/chio-labs/streambuild/commit/e3546b20f014de1e8ba504a6a11ae1501c5df5aa))
* dev_server core - compile state, status, reload, definitions ([60a0d93](https://github.com/chio-labs/streambuild/commit/60a0d93da7d73f6b33986d8348f43036e2604746))
* dev_server live state - the /api/state warehouse overlay ([036b947](https://github.com/chio-labs/streambuild/commit/036b947661836a691edd4501054870bf4b9f2234))
* dev_server plan, checks, and run history endpoints ([50f1ecd](https://github.com/chio-labs/streambuild/commit/50f1ecdbbeba4e7200e9138bcb216f543d8211fc))
* execute from the UI — plan Execute, live run page, lineage run panel ([e571f64](https://github.com/chio-labs/streambuild/commit/e571f642d6ff85a7f826176a2439cdb0306d928a))
* give stb dev a terminal voice — startup banner and live activity feed ([deab811](https://github.com/chio-labs/streambuild/commit/deab811b0f2cb508fa5a02f2ee37e11763a5eaaa))
* honest plan numbers, stb --version, and remaining dev UI gaps ([e49c965](https://github.com/chio-labs/streambuild/commit/e49c965ff477c2a306daa4e222361481fe1dc212))
* POST /api/build — single-flight subprocess execution with live feed ([6608506](https://github.com/chio-labs/streambuild/commit/6608506e4b44e29c71c768b9138392dcd71b2a6f))
* remove the direct-build preflight phase and retention coverage state ([1bc7fd3](https://github.com/chio-labs/streambuild/commit/1bc7fd365c57992aaf91cf90bbb7bacae7b2331f))


### Bug Fixes

* dev UI — dead controls, shallow-routing filters, and fabricated data ([b354595](https://github.com/chio-labs/streambuild/commit/b354595ac677ce0e8a397b32631cc243e22904f9))
* honest timestamps, live runs list, and Ctrl+C leaves a record ([f351fde](https://github.com/chio-labs/streambuild/commit/f351fde4577915acacdeb847c81abf75309835d8))
* preserve UTC replay start times ([b333bf7](https://github.com/chio-labs/streambuild/commit/b333bf7d76743426368855b2abbb171384149808))

## [0.6.0](https://github.com/chio-labs/streambuild/compare/v0.5.0...v0.6.0) (2026-08-03)


### Features

* add append-only metadata history ([7a2807c](https://github.com/chio-labs/streambuild/commit/7a2807c27c4860b59fba909be3fbd13585d7d632))
* enforce observability non-authority ([ae32f2f](https://github.com/chio-labs/streambuild/commit/ae32f2f03be627ac872f4bf7fb17313eeafa8051))

## [0.5.0](https://github.com/chio-labs/streambuild/compare/v0.4.0...v0.5.0) (2026-08-02)


### Features

* support bounded direct start times ([8468e83](https://github.com/chio-labs/streambuild/commit/8468e8312ed4761c059e480b7477d59682be1f77))
* support bounded direct start times ([a23c85c](https://github.com/chio-labs/streambuild/commit/a23c85cc8d816a14db49970d53adaed8cd0b498d))

## [0.4.0](https://github.com/chio-labs/streambuild/compare/v0.3.0...v0.4.0) (2026-08-02)


### Features

* enforce executable build workflows ([179a2c7](https://github.com/chio-labs/streambuild/commit/179a2c76f15425980fc7312f4d4f2761f3bd8159))
* expose exact plan workflows ([1d8df01](https://github.com/chio-labs/streambuild/commit/1d8df011238cc220a0fe795ac5774b78aa62411c))
* persist connected plan artifacts ([7ac3f8a](https://github.com/chio-labs/streambuild/commit/7ac3f8aa462eb2a1723001ccdbe5c0805efa20cb))
* unify mode-aware builds ([2b6434f](https://github.com/chio-labs/streambuild/commit/2b6434f44c57a66c2c73b8052cab12ae994a7f78))

## [0.3.0](https://github.com/chio-labs/streambuild/compare/v0.2.0...v0.3.0) (2026-08-01)


### Features

* add terminal view models ([f2b1974](https://github.com/chio-labs/streambuild/commit/f2b1974a5d0f9ad25bbf615675e6cb521e1b3f6a))


### Bug Fixes

* use warehouse time for replay boundaries ([c6d6a78](https://github.com/chio-labs/streambuild/commit/c6d6a7815122bbb80342aae61e3450a7e6b277e0))

## [0.2.0](https://github.com/chio-labs/streambuild/compare/v0.1.0...v0.2.0) (2026-07-31)


### Features

* add adopted-source standard builds ([f14de47](https://github.com/chio-labs/streambuild/commit/f14de47874e52dcff4e9da18bb163541eca97401))
* add managed source TTL configuration ([28a9cec](https://github.com/chio-labs/streambuild/commit/28a9cec67835d108a26b4c9cf4279411873de0af))
* add standard-mode plan with scope, ownership, and replay roots ([5357baa](https://github.com/chio-labs/streambuild/commit/5357baa12da3587d0a4c147bc10bf19e5d6b925a))
* add standard-mode stb build with ownership and boundary contract ([d8a1a21](https://github.com/chio-labs/streambuild/commit/d8a1a21c45c6525ecea39cf95b869813303e29cd))
* adopt direct mode and SQLBuild model headers ([8d31827](https://github.com/chio-labs/streambuild/commit/8d318276106ce18131f7a548ced14fd89dba9e17))
* complete standard build rerun recovery ([f3d1c53](https://github.com/chio-labs/streambuild/commit/f3d1c539267e443f2b344c96e66e8e69f70d1e78))
* complete standard selected downstream rebuild ([f930cc1](https://github.com/chio-labs/streambuild/commit/f930cc11b68912f7835d0eeb2f71fd5ee55db101))
* gate commands by effective mode ([4c30d0a](https://github.com/chio-labs/streambuild/commit/4c30d0a7ed74e75cf2c9eb13948522c776407b80))
* infer pipeline sources from models ([178beb2](https://github.com/chio-labs/streambuild/commit/178beb290f8a971b3396c86766e814be277cd2e2))
* initialize StreamBuild project ([c63ff98](https://github.com/chio-labs/streambuild/commit/c63ff9849303c6ae529fdf8a352febb253ba0a50))
* mature chained SQL tests and macro tests ([d511082](https://github.com/chio-labs/streambuild/commit/d5110827123c93bef52e2992dc5e41edd67103f6))
* migrate remaining SQL analysis to Polyglot ([7750bb1](https://github.com/chio-labs/streambuild/commit/7750bb1e4a463fe26eefc50c3232351a61dd0320))
* migrate replay SQL to Polyglot ([757845f](https://github.com/chio-labs/streambuild/commit/757845f5f326b2bacf2b9f5c6f3b412bff5e9d00))
* rename CLI command to stb ([4bf2f64](https://github.com/chio-labs/streambuild/commit/4bf2f642e850188fe344e364bfdc20378ec2f6bf))
* unify replay population execution ([9e1a14d](https://github.com/chio-labs/streambuild/commit/9e1a14d202ffa0af88a24b680b35a022d9d0feff))


### Bug Fixes

* lint the standard build package that gitignore had hidden ([d6b673f](https://github.com/chio-labs/streambuild/commit/d6b673f24c014ccda705508d95f925d341df5377))
* remediate migration regressions ([7f5b61b](https://github.com/chio-labs/streambuild/commit/7f5b61b07675bf6de796b5e5ae642288b6326a23))
* repair the CLI output preview script and split it into a package ([f1e79c2](https://github.com/chio-labs/streambuild/commit/f1e79c20e9cbeea3d38c1dd540e5232ea6439544))


### Documentation

* add StreamBuild logo ([b21ee99](https://github.com/chio-labs/streambuild/commit/b21ee990f19b44f49756a369423c768b9448a4c6))
* polish publication-facing guidance ([c346c20](https://github.com/chio-labs/streambuild/commit/c346c20647eb23b85de6739708f0f35451d023d6))
