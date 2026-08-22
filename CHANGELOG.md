# Changelog

## [0.26.3](https://github.com/chio-labs/streambuild/compare/v0.26.2...v0.26.3) (2026-08-22)


### Bug Fixes

* **release:** satisfy protected release merges ([#140](https://github.com/chio-labs/streambuild/issues/140)) ([f302d4c](https://github.com/chio-labs/streambuild/commit/f302d4cf608bcb5693baaf735fe8eb4ba210c3d1))

## [0.26.2](https://github.com/chio-labs/streambuild/compare/v0.26.1...v0.26.2) (2026-08-22)


### Build System

* **release:** standardize automated releases ([#138](https://github.com/chio-labs/streambuild/issues/138)) ([c8d1128](https://github.com/chio-labs/streambuild/commit/c8d11280a656fa7c70b7c6df1c9815467087c91e))

## [0.26.1](https://github.com/chio-labs/streambuild/compare/v0.26.0...v0.26.1) (2026-08-21)


### Bug Fixes

* **ui:** suppress transient telemetry warnings ([#136](https://github.com/chio-labs/streambuild/issues/136)) ([276a5e3](https://github.com/chio-labs/streambuild/commit/276a5e3dfd30eef9c1559fa6bb30817453babee6))

## [0.26.0](https://github.com/chio-labs/streambuild/compare/v0.25.1...v0.26.0) (2026-08-21)


### Features

* improve UI responsiveness and audit operations ([abadd65](https://github.com/chio-labs/streambuild/commit/abadd65a056581a0adb7e9f8904fcf8e9d0221d4))
* show live run and audit cycle progress ([0aa14b5](https://github.com/chio-labs/streambuild/commit/0aa14b5592ab4f00592204872390a3716ab976ff))


### Bug Fixes

* **audits:** defer unmaterialized relations ([5ab6371](https://github.com/chio-labs/streambuild/commit/5ab6371cdbecd89b81d4d79544c19e588471705e))
* **audits:** reconcile stale builds across releases ([c973de2](https://github.com/chio-labs/streambuild/commit/c973de2b74780eed8119028b4a0f0a6b611c8e36))
* **ui:** defer project shell until bootstrap completes ([001286c](https://github.com/chio-labs/streambuild/commit/001286cf04f269cb088ba616dc393990e64ab378))
* **ui:** prevent runs startup refresh loop ([1c1569b](https://github.com/chio-labs/streambuild/commit/1c1569b4368037cc9814606fbfd1a5b5e93b794c))
* **ui:** require cached definitions for conditional reads ([2d2f38f](https://github.com/chio-labs/streambuild/commit/2d2f38fb42126b7a985a888d4491906b9f2c9826))


### Performance Improvements

* **auth:** cache resolved request identities ([995cb07](https://github.com/chio-labs/streambuild/commit/995cb07341c6e6a31850c0df398d9a4afa9fd5c3))
* **plan:** isolate reads and defer replay counts ([ffaa5c5](https://github.com/chio-labs/streambuild/commit/ffaa5c5b9f10af4cdadacff9feec53797f89c9fd))
* **ui:** deduplicate live refresh requests ([3f5467d](https://github.com/chio-labs/streambuild/commit/3f5467d964dd65b2877bcb5c09d885becef7a938))
* **ui:** split auth and cache definitions ([e4a35cb](https://github.com/chio-labs/streambuild/commit/e4a35cba11cc3deb4f0302f906830b692527ec9f))
* **ui:** standardize cached page navigation ([428fbed](https://github.com/chio-labs/streambuild/commit/428fbed691dcf24df8c0314384ac867689abba90))

## [0.25.1](https://github.com/chio-labs/streambuild/compare/v0.25.0...v0.25.1) (2026-08-21)


### Bug Fixes

* **compile:** reject prewhere in table models ([6b52b2a](https://github.com/chio-labs/streambuild/commit/6b52b2aac8658618d0342fca95990f2b2d499436))
* **replay:** filter non-lineage roots at source ([eb3cb12](https://github.com/chio-labs/streambuild/commit/eb3cb12af4d368d79b9a612ad5bb9da1fda60bb7))

## [0.25.0](https://github.com/chio-labs/streambuild/compare/v0.24.5...v0.25.0) (2026-08-21)


### Features

* **replay:** add phase-scoped execution settings ([83d746e](https://github.com/chio-labs/streambuild/commit/83d746e3e14da4d8a365bfc6ef0ac9e4c93d427d))

## [0.24.5](https://github.com/chio-labs/streambuild/compare/v0.24.4...v0.24.5) (2026-08-20)


### Performance Improvements

* **ui:** initialize the project in one request ([70d6124](https://github.com/chio-labs/streambuild/commit/70d6124462d0f160c9d9aa651c15207156871cd8))

## [0.24.4](https://github.com/chio-labs/streambuild/compare/v0.24.3...v0.24.4) (2026-08-20)


### Performance Improvements

* **ui:** render before secondary warehouse data loads ([4bc9ee6](https://github.com/chio-labs/streambuild/commit/4bc9ee65f065e4bb23b5c0f2169268a59c4a6d9c))

## [0.24.3](https://github.com/chio-labs/streambuild/compare/v0.24.2...v0.24.3) (2026-08-20)


### Performance Improvements

* **dev-server:** build the warehouse overlay off the shared query lock ([63f504f](https://github.com/chio-labs/streambuild/commit/63f504fa4541d89b29e72f26510282dad238106b))

## [0.24.2](https://github.com/chio-labs/streambuild/compare/v0.24.1...v0.24.2) (2026-08-20)


### Bug Fixes

* **dev-server:** keep the state overlay across warehouse refreshes ([908bc3b](https://github.com/chio-labs/streambuild/commit/908bc3b026316ad96a47bf78dae6ac6b466c90e8))
* **dev-server:** only force a snapshot rebuild on explicit refresh ([3efc5a5](https://github.com/chio-labs/streambuild/commit/3efc5a512f9ac63760f72b4417e0d84c3b09de8c))

## [0.24.1](https://github.com/chio-labs/streambuild/compare/v0.24.0...v0.24.1) (2026-08-20)


### Bug Fixes

* **dev-server:** serialize nested connection settings ([5834f79](https://github.com/chio-labs/streambuild/commit/5834f793f47aa7d6138cdea114028480709884d3))

## [0.24.0](https://github.com/chio-labs/streambuild/compare/v0.23.0...v0.24.0) (2026-08-20)


### Features

* **adapter:** send configured ClickHouse session settings ([0d672d4](https://github.com/chio-labs/streambuild/commit/0d672d4116ff99e47db33388eec6e47b3cc81600))


### Bug Fixes

* **cli:** stop claiming --start-time is virtual only ([e5c9582](https://github.com/chio-labs/streambuild/commit/e5c95828793c6fec55345769d36e62278667adc1))
* **compiler:** stop consuming the retained tree when resolving aliased refs ([18feb0d](https://github.com/chio-labs/streambuild/commit/18feb0da59fb6fa018a546658ac25cd09c592dc2))


### Performance Improvements

* **compiler:** collect every model tree fact in one traversal ([664b33f](https://github.com/chio-labs/streambuild/commit/664b33f7fb95a2f2085cc7dd702e29c0a56b31e4))
* **compiler:** reach SQLBuild compile parity by removing unread analysis work ([65bce29](https://github.com/chio-labs/streambuild/commit/65bce29fb218f45ffb7169d8e64e912242a0922e))
* **compiler:** resolve each model tree in one traversal ([fabf1e1](https://github.com/chio-labs/streambuild/commit/fabf1e112ecec5a8f3555e7025098f3e631d5139))
* **compiler:** resolve references by substitution instead of rendering ([a703c01](https://github.com/chio-labs/streambuild/commit/a703c01afec5f5b356a7c22d05592deed2bd7fbc))
* **compiler:** restore the dropped SQLBuild scanner skip and stop re-walking trees ([6e1ca2c](https://github.com/chio-labs/streambuild/commit/6e1ca2cb2a90b9a96178a7c7f1c400e78cb0b1ce))
* **compiler:** restore the reference scanner skip and stop deep copying trees ([3716397](https://github.com/chio-labs/streambuild/commit/3716397ae1c2355e9ce66b40ee6a232177a8b332))
* **compiler:** stop rendering canonical SQL that nothing reads ([39d8582](https://github.com/chio-labs/streambuild/commit/39d8582badc82104b4d8128e43d32acf9db53138))
* **compiler:** walk each parsed model tree once per purpose ([a9df82f](https://github.com/chio-labs/streambuild/commit/a9df82f7da176690c63de455ef8209cb4ced820d))
* **dev-server:** serve one background-refreshed warehouse overlay ([3c5e703](https://github.com/chio-labs/streambuild/commit/3c5e70343ec85afae776626077168645c266e057))

## [0.23.0](https://github.com/chio-labs/streambuild/compare/v0.22.4...v0.23.0) (2026-08-19)


### Features

* **adapter:** prove refreshable views against clickhouse and report their state ([ea6a4e9](https://github.com/chio-labs/streambuild/commit/ea6a4e938cdd23872a9ba7077f8667fbd36a9432))
* **adapter:** realize scheduled postgres sources as refreshable views ([0a206b4](https://github.com/chio-labs/streambuild/commit/0a206b42c7170fd1263e43ac52ef5f28e559a3f8))
* **compiler:** discover scheduled postgres refresh sources ([ddafdd4](https://github.com/chio-labs/streambuild/commit/ddafdd4973920777813fd9836c3cdd7df24463f5))
* scheduled Postgres refresh sources (CHI-56) ([c6f85d1](https://github.com/chio-labs/streambuild/commit/c6f85d172bac9ef048e6988f43c4273a29361a2b))


### Bug Fixes

* **auth:** resolve proxy identities that a competing writer just linked ([e40ebda](https://github.com/chio-labs/streambuild/commit/e40ebdad16692bd5562fc38d60ca39f773c3f04e))
* **clickhouse:** test against the ClickHouse version production runs ([f8fe102](https://github.com/chio-labs/streambuild/commit/f8fe1024c3b6a37fcf7cfdad6bbd8a2ecc004b24))
* **e2e:** expect the sqlbuild-style select list the run dialog builds ([c0fd059](https://github.com/chio-labs/streambuild/commit/c0fd059bff308c0d551b34d73ad294c7b1b184cd))
* **ui:** never render a stale plan behind a plan error ([709379d](https://github.com/chio-labs/streambuild/commit/709379d2b31b79758633a0dc8317e7aaad8060ca))

## [0.22.4](https://github.com/chio-labs/streambuild/compare/v0.22.3...v0.22.4) (2026-08-19)


### Bug Fixes

* **ui:** derive plan command locally and gate stale plan behind loading ([53fb74d](https://github.com/chio-labs/streambuild/commit/53fb74d1b11dbf1d6070ebef0483a9134013afd5))
* **ui:** show loading spinner instead of compile flash on live run detail ([927d2d4](https://github.com/chio-labs/streambuild/commit/927d2d44f76d657e942910382b8cbd6729f35d22))

## [0.22.3](https://github.com/chio-labs/streambuild/compare/v0.22.2...v0.22.3) (2026-08-19)


### Bug Fixes

* **cli:** resolve --select as a global name list with pipeline/model sugar ([85aaa52](https://github.com/chio-labs/streambuild/commit/85aaa521f945c2e2c014490271d4f3626f3e7494))
* sqlbuild-style --select (name lists + bare pipeline names) and safe selection ([1cc750f](https://github.com/chio-labs/streambuild/commit/1cc750f26b267348bb377db0613ea0e433d76e97))
* **ui:** accept --select lists and bare pipeline names; generate one --select ([8c1f81d](https://github.com/chio-labs/streambuild/commit/8c1f81d901d7e5517346095e2f47568df3c1c9c9))

## [0.22.2](https://github.com/chio-labs/streambuild/compare/v0.22.1...v0.22.2) (2026-08-18)


### Bug Fixes

* **compiler:** conjoin replay predicates into the outer WHERE clause ([fd1db10](https://github.com/chio-labs/streambuild/commit/fd1db10b04d86683db119997eca4541e6ccafa44))
* **compiler:** preserve author bytes through replay and shadow SQL rewrites ([8f51d83](https://github.com/chio-labs/streambuild/commit/8f51d83a11762b7a13338492ed27bf8d541b1294))
* **compiler:** preserve authored SQL bytes in executed database templates ([312c716](https://github.com/chio-labs/streambuild/commit/312c716ce955bdf5de2b660791b9480cdd962d1f))
* **compiler:** reject raw model relations and scope union CTE visibility ([dfa0945](https://github.com/chio-labs/streambuild/commit/dfa0945452d157c9f579e476cd6c18b83b9dd12b))

## [0.22.1](https://github.com/chio-labs/streambuild/compare/v0.22.0...v0.22.1) (2026-08-18)


### Bug Fixes

* **observability:** persist full run errors and enlarge the error dialog ([8cc6896](https://github.com/chio-labs/streambuild/commit/8cc6896e2d106afa260a0dbd127bd3b6b3b3ad83))

## [0.22.0](https://github.com/chio-labs/streambuild/compare/v0.21.3...v0.22.0) (2026-08-18)


### Features

* show executed SQL in run timelines ([4d3d10a](https://github.com/chio-labs/streambuild/commit/4d3d10ab3f744291079fabffd5b14411906d9466))
* **ui:** expandable/modal error viewer for runs and deployments (CHI-52) ([66ab83c](https://github.com/chio-labs/streambuild/commit/66ab83cb558f5ebf91c7fa88d65ab5bde8138464))


### Bug Fixes

* **observability:** skip run-statement persistence when the adapter renders none ([74b68d3](https://github.com/chio-labs/streambuild/commit/74b68d30777744a326920d56ecd7c7c94408ff4c))

## [0.21.3](https://github.com/chio-labs/streambuild/compare/v0.21.2...v0.21.3) (2026-08-18)


### Bug Fixes

* surface pending warehouse outages ([adede0c](https://github.com/chio-labs/streambuild/commit/adede0ca29ef803dfa19b9e32c49f4d2d191d110))

## [0.21.2](https://github.com/chio-labs/streambuild/compare/v0.21.1...v0.21.2) (2026-08-18)


### Bug Fixes

* keep the dev UI available through warehouse outages ([e9bc7dd](https://github.com/chio-labs/streambuild/commit/e9bc7dd6deebedeeb91f325c6afdf44fe983aa5c))

## [0.21.1](https://github.com/chio-labs/streambuild/compare/v0.21.0...v0.21.1) (2026-08-17)


### Bug Fixes

* allow disabled authentication on shared bind addresses ([b511d93](https://github.com/chio-labs/streambuild/commit/b511d93ba56cdcefdead297d09066e1fecd959e8))

## [0.21.0](https://github.com/chio-labs/streambuild/compare/v0.20.0...v0.21.0) (2026-08-16)


### Features

* add a tick timeline to the sensor detail page ([ce105ba](https://github.com/chio-labs/streambuild/commit/ce105baa82b37ce2d3f108122c21410b3ded1c66))
* add authentication policy and durable sensors ([d516bce](https://github.com/chio-labs/streambuild/commit/d516bce8a046eee667ebad2d36dbc36bbb82f8bf))
* align sensors and users pages with the list design language ([64d2120](https://github.com/chio-labs/streambuild/commit/64d212023511690bf88e9d81371b38ec72d167fe))
* explain dead letters in the sensor detail panel ([0ff8783](https://github.com/chio-labs/streambuild/commit/0ff8783277c3157618d5ef56a9b862918acb211e))
* give each sensor a dedicated detail page ([1a86ffb](https://github.com/chio-labs/streambuild/commit/1a86ffbe06a070b26ca8c7a9bdd4d168ef977f56))
* make the tick timeline a zoomable time axis ([a5b15f7](https://github.com/chio-labs/streambuild/commit/a5b15f77af69af045765bc935e84aa0dc2672590))
* move dead letters into the sensor detail panel ([f3cc663](https://github.com/chio-labs/streambuild/commit/f3cc66336f77ee3be1196c36abe8d13c1ab9be50))
* redesign users and sensors pages ([9e2c9aa](https://github.com/chio-labs/streambuild/commit/9e2c9aa779f8b5042649f8e144531e01f32367e2))


### Bug Fixes

* harden authentication and authorization boundaries ([378733f](https://github.com/chio-labs/streambuild/commit/378733ff0b1446befa6eeb394b8b9a6df067b47d))

## [0.20.0](https://github.com/chio-labs/streambuild/compare/v0.19.1...v0.20.0) (2026-08-11)


### Features

* make Plan UI mode aware ([370ba8b](https://github.com/chio-labs/streambuild/commit/370ba8b9a429f749dffc7166097bd1561c63be7f))

## [0.19.1](https://github.com/chio-labs/streambuild/compare/v0.19.0...v0.19.1) (2026-08-11)


### Bug Fixes

* show full run ID on detail page ([39f4a3a](https://github.com/chio-labs/streambuild/commit/39f4a3adf2ffb4500f98116011bc725a8d90d471))

## [0.19.0](https://github.com/chio-labs/streambuild/compare/v0.18.1...v0.19.0) (2026-08-11)


### Features

* add build safety guardrails ([193aa2a](https://github.com/chio-labs/streambuild/commit/193aa2a5b6d87a420f8ef754943a98d6ababda87))
* enforce global pipeline naming uniqueness ([0dc5b62](https://github.com/chio-labs/streambuild/commit/0dc5b624e8ce5b7233207b277d45a27606c75092))


### Documentation

* tighten pipeline naming guidance ([1c67487](https://github.com/chio-labs/streambuild/commit/1c67487e7f848ecfd6c91a6ce3da3ae8e52bc14d))

## [0.18.1](https://github.com/chio-labs/streambuild/compare/v0.18.0...v0.18.1) (2026-08-10)


### Bug Fixes

* align deployment inventory columns ([d40f82b](https://github.com/chio-labs/streambuild/commit/d40f82b86ac41978531c9bc91f9417c591fe611f))
* preserve lineage activity and viewport ([c4a259c](https://github.com/chio-labs/streambuild/commit/c4a259c84880e492b60cb901a9bab0296774ea28))

## [0.18.0](https://github.com/chio-labs/streambuild/compare/v0.17.0...v0.18.0) (2026-08-10)


### Features

* render Plan before warehouse planning ([3ed7c05](https://github.com/chio-labs/streambuild/commit/3ed7c052c4273e33e87d0cd73e177ede6382da7f))

## [0.17.0](https://github.com/chio-labs/streambuild/compare/v0.16.6...v0.17.0) (2026-08-09)


### Features

* add lineage activity telemetry ([c390acd](https://github.com/chio-labs/streambuild/commit/c390acda03bb8c29906fa9b1bd799118daa4b08e))

## [0.16.6](https://github.com/chio-labs/streambuild/compare/v0.16.5...v0.16.6) (2026-08-09)


### Bug Fixes

* harden lineage rebuild safety ([518b3af](https://github.com/chio-labs/streambuild/commit/518b3af294e28de6c0bfe34d84d77a7fa5ea4c3e))
* scope active build conflicts ([c73fabb](https://github.com/chio-labs/streambuild/commit/c73fabbad216a3c7cf0aa2dab63e6271b41ea046))


### Documentation

* streamline project overview ([01f3971](https://github.com/chio-labs/streambuild/commit/01f397118ff52b9ef918862659bb7a52447e67a7))

## [0.16.5](https://github.com/chio-labs/streambuild/compare/v0.16.4...v0.16.5) (2026-08-09)


### Bug Fixes

* clarify stalled run recovery ([013ea96](https://github.com/chio-labs/streambuild/commit/013ea96636336098c166e9a64342f18efba377cb))

## [0.16.4](https://github.com/chio-labs/streambuild/compare/v0.16.3...v0.16.4) (2026-08-09)


### Bug Fixes

* align execution UI with runtime state ([600c683](https://github.com/chio-labs/streambuild/commit/600c683b1f03db35422634fdd55957b05c771d17))

## [0.16.3](https://github.com/chio-labs/streambuild/compare/v0.16.2...v0.16.3) (2026-08-09)


### Bug Fixes

* clarify promotion run events ([8f6ae31](https://github.com/chio-labs/streambuild/commit/8f6ae31d23efa5bffa9d610f04ad837f1713253d))
* humanize run event timeline ([d822320](https://github.com/chio-labs/streambuild/commit/d822320a06da8a1f4df97b2bffc331116a8686d4))

## [0.16.2](https://github.com/chio-labs/streambuild/compare/v0.16.1...v0.16.2) (2026-08-09)


### Bug Fixes

* clarify initial deployment publishing ([45408d4](https://github.com/chio-labs/streambuild/commit/45408d4e6ff4f3a18e3048a49ff5610167d749a3))
* stabilize scheduler and run state ([729f975](https://github.com/chio-labs/streambuild/commit/729f9754017fe5e0143204b561511546b0d6e9d1))

## [0.16.1](https://github.com/chio-labs/streambuild/compare/v0.16.0...v0.16.1) (2026-08-09)


### Bug Fixes

* stabilize UI loading transitions ([5e0562e](https://github.com/chio-labs/streambuild/commit/5e0562e5c1868873a862245c50aadaaa4d755fca))

## [0.16.0](https://github.com/chio-labs/streambuild/compare/v0.15.0...v0.16.0) (2026-08-09)


### Features

* improve UI loading and scheduler status ([e6b1446](https://github.com/chio-labs/streambuild/commit/e6b1446e5955747b19508e653b22588b7652a4a4))


### Bug Fixes

* scope direct source preparation to selection ([28206e1](https://github.com/chio-labs/streambuild/commit/28206e1f219912d93c565528585ece6c5023dbfd))

## [0.15.0](https://github.com/chio-labs/streambuild/compare/v0.14.1...v0.15.0) (2026-08-09)


### Features

* scope Kafka consumer groups by target ([fc7f7c4](https://github.com/chio-labs/streambuild/commit/fc7f7c48b982d071b41270b48e5c6a2e2f39bc86))

## [0.14.1](https://github.com/chio-labs/streambuild/compare/v0.14.0...v0.14.1) (2026-08-09)


### Bug Fixes

* serialize immutable mappings in fingerprints ([3f6d68a](https://github.com/chio-labs/streambuild/commit/3f6d68a40b0ff87d610f18621a61f0fe12ccadc0))

## [0.14.0](https://github.com/chio-labs/streambuild/compare/v0.13.0...v0.14.0) (2026-08-09)


### Features

* complete virtual deployment lifecycle ([acfbf58](https://github.com/chio-labs/streambuild/commit/acfbf5835b74113e65bf8135c01fd5e0ce1e0c30))
* derive Kafka source names with macros ([e30223d](https://github.com/chio-labs/streambuild/commit/e30223d4ce955fb554ee0ebe7fd1103625944f63))
* expose deployment promote, cleanup and diff over the dev API ([71f3372](https://github.com/chio-labs/streambuild/commit/71f33723150ad89f1cdb195487cf0e0c9d03a2fb))
* promote, clean up and diff deployments from the UI ([d8231f3](https://github.com/chio-labs/streambuild/commit/d8231f3c3d663e7cfd76697a0e52fef9ed351b56))
* show deployment relations and orphans in the physical view ([e8e6414](https://github.com/chio-labs/streambuild/commit/e8e64142f007f6eee82ed80d68aea69fc8a9eeb3))
* show the switchover model by model on the run page ([1a46901](https://github.com/chio-labs/streambuild/commit/1a469018c5356cd9a2972c313a604ba58f2d3a32))
* surface virtual deployments in the dev UI ([5d64f69](https://github.com/chio-labs/streambuild/commit/5d64f692c71c25a8bebb5e339565315e6b49be3e))


### Bug Fixes

* measure virtual-mode models by the relation they are bound to ([914a48c](https://github.com/chio-labs/streambuild/commit/914a48c203f089594e8c67560f72958ca23215ae))
* offer rollback on superseded deployments ([83c128a](https://github.com/chio-labs/streambuild/commit/83c128a836cbd053ea02b3489d0235bf77a451ea))

## [0.13.0](https://github.com/chio-labs/streambuild/compare/v0.12.4...v0.13.0) (2026-08-08)


### Features

* add per-pipeline build modes ([95b892c](https://github.com/chio-labs/streambuild/commit/95b892cbf3d63b1f172eed1e16a697f1a203a409))

## [0.12.4](https://github.com/chio-labs/streambuild/compare/v0.12.3...v0.12.4) (2026-08-08)


### Bug Fixes

* label the overview source card row count as rows ([7570be8](https://github.com/chio-labs/streambuild/commit/7570be87610918b267a1ef0be960203e978a3d5f))
* reset offsets for fresh source landings ([6a61125](https://github.com/chio-labs/streambuild/commit/6a61125ea6452b936fe4cacb4bfe3f14c811dca1))

## [0.12.3](https://github.com/chio-labs/streambuild/compare/v0.12.2...v0.12.3) (2026-08-08)


### Bug Fixes

* adopt Console-style payload view, stable columns, and match highlighting ([a8c7955](https://github.com/chio-labs/streambuild/commit/a8c79555a297b16597e77b1b7553ff1f900a453b))
* always show broker timestamp and make message columns sortable ([b98ee7e](https://github.com/chio-labs/streambuild/commit/b98ee7ebd8f58086122cfb5457bf6f4b708ea30a))
* paginate the message list and default to broker timestamp order ([a2237da](https://github.com/chio-labs/streambuild/commit/a2237dac9344f0ad2569cbeeee2f606ff4d27c90))
* raise the full-record cap to 16 MiB ([b7ffc03](https://github.com/chio-labs/streambuild/commit/b7ffc03c6f8e590192988283ea1b35cbe55ee007))

## [0.12.2](https://github.com/chio-labs/streambuild/compare/v0.12.1...v0.12.2) (2026-08-08)


### Bug Fixes

* gate topics navigation on the first inventory load ([8712dd4](https://github.com/chio-labs/streambuild/commit/8712dd4edb4a9e50ff6dae9fa6581a430023f712))
* keep dev app startup warmer within comment policy ([e04bcc6](https://github.com/chio-labs/streambuild/commit/e04bcc6d4ddab1c94ba7dbf8b1fc8bc491051255))
* keep the topics inventory across navigations ([d6c22c4](https://github.com/chio-labs/streambuild/commit/d6c22c4171885a9f7ad1248833b799cec254b8bf))

## [0.12.1](https://github.com/chio-labs/streambuild/compare/v0.12.0...v0.12.1) (2026-08-08)


### Bug Fixes

* default topics page to managed topics and link topic names ([3582faf](https://github.com/chio-labs/streambuild/commit/3582faf5568e898c517628ea247828ed89455cf5))
* stabilise message browser layout and adopt debounced auto-search ([4f820dd](https://github.com/chio-labs/streambuild/commit/4f820ddfa20706eb67e6948c25715b001b42c247))
* warm broker metadata caches at dev server startup ([1226094](https://github.com/chio-labs/streambuild/commit/12260948713566cfc0b3450d86ba7f16c997f881))

## [0.12.0](https://github.com/chio-labs/streambuild/compare/v0.11.0...v0.12.0) (2026-08-08)


### Features

* add source message browser and topics inventory ([40afebe](https://github.com/chio-labs/streambuild/commit/40afebe06d82645899671e5843d462efc28bf2f0))

## [0.11.0](https://github.com/chio-labs/streambuild/compare/v0.10.0...v0.11.0) (2026-08-08)


### Features

* add quality identities and audit scheduling ([d9b88ba](https://github.com/chio-labs/streambuild/commit/d9b88ba73c22302eb7f65ce9561d4270d097ff0a))


### Bug Fixes

* guard empty Release Please outputs ([32b9cb6](https://github.com/chio-labs/streambuild/commit/32b9cb691c53862aa87b7bdb43a720b715cecd79))

## [0.10.0](https://github.com/chio-labs/streambuild/compare/v0.9.3...v0.10.0) (2026-08-08)


### Features

* add pipeline safeguards and Kafka observability ([124f735](https://github.com/chio-labs/streambuild/commit/124f7353463e0ac487de9d56f7ce624d03d0908e))

## [0.9.3](https://github.com/chio-labs/streambuild/compare/v0.9.2...v0.9.3) (2026-08-07)


### Bug Fixes

* keep release lockfile synchronized ([ac15b72](https://github.com/chio-labs/streambuild/commit/ac15b721cc476918052eeb73b3be0c835214601d))

## [0.9.2](https://github.com/chio-labs/streambuild/compare/v0.9.1...v0.9.2) (2026-08-07)


### Bug Fixes

* complete plan replay window controls ([37b31d0](https://github.com/chio-labs/streambuild/commit/37b31d03c08a2fa1634ad6be6d452256a421fcf5))
* harden API and missing run states ([fa842f1](https://github.com/chio-labs/streambuild/commit/fa842f1bfa43827982ae7406eeadba23e9fbefe3))
* make core UI usable on mobile ([ced9a42](https://github.com/chio-labs/streambuild/commit/ced9a428cc5c0f3e00b20fdbc5ec01e269c5a6ae))

## [0.9.1](https://github.com/chio-labs/streambuild/compare/v0.9.0...v0.9.1) (2026-08-07)


### Bug Fixes

* align dev UI with persisted model state ([c534296](https://github.com/chio-labs/streambuild/commit/c5342965109b673f583e7a1ee1bba9e5efcf080d))
* pin development Python to 3.12 ([1b83a6e](https://github.com/chio-labs/streambuild/commit/1b83a6e57b713fc589604372068bb72f91842541))
* refresh lockfile project version ([0cb2b24](https://github.com/chio-labs/streambuild/commit/0cb2b24ba5e068744bbcc96f62e1bdec6ba8f2ce))

## [0.9.0](https://github.com/chio-labs/streambuild/compare/v0.8.0...v0.9.0) (2026-08-07)


### Features

* improve CLI plan and error presentation ([74d1b62](https://github.com/chio-labs/streambuild/commit/74d1b6265c5eaf0dbe23f562e204c1679d7aa952))


### Bug Fixes

* package dev UI assets in distributions ([1cb9a84](https://github.com/chio-labs/streambuild/commit/1cb9a84576f6633edcd21a513334b619ef8a651a))

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
