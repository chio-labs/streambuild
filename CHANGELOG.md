# Changelog

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
