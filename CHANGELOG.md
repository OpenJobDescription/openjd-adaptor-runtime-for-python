## 0.8.1 (2024-11-13)


### Features
* Adding optional override for adaptor request timeout default to EntryPoint start method (#149) ([`652164f`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/652164f672a8548ee1f89e430b90378d06bbea34))


## 0.8.0 (2024-06-03)

### BREAKING CHANGES
* handle socket name collisions (#125) ([`a123717`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/a1237171d2fe86e99b4eed5fd7f6f9578ff24aa9))



## 0.7.2 (2024-04-24)

### CI
* add PyPI publish job to publish workflow (#118) ([`1c7cfb7`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/1c7cfb77555e958cd6343bff445aacf657d32bbb))


## 0.7.1 (2024-04-23)



### Bug Fixes
* set correct permission for the test directory. (#107) ([`169f346`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/169f346df8efc5bbcc33eda9859c4bb20fe471f4))

## 0.7.0 (2024-04-01)

### BREAKING CHANGES
* public release (#101) ([`c9be773`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/c9be773e212f6d0b505a2eb52d9a4fde63a476c1))



## 0.6.1 (2024-03-25)



### Bug Fixes
* Add `delete` permission to the`secure_open` (#92) ([`6d066ad`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/6d066ad98f33e1b54a6934c1d244f5938a65ec90))

## 0.6.0 (2024-03-22)


### BREAKING CHANGES
* Move the `named_pipe_helper.py` under the folder `adaptor_runtime_client` (#87) ([`1398c56`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/1398c562fead13564705329838a377468e11c2c1))


### Bug Fixes
* Update request method in windows Client interface to blocking call. (#90) ([`e66d592`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/e66d5927f6f0ede574ae39bcd2616042265baa7c))
* increase max named pipe instances to 4 (#91) ([`7440c53`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/7440c531f3eadabd9496217ad37f7247e17f5358))
* specify max named pipe instances (#86) ([`d959381`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/d95938179b4f605d9315cecec8b80b52f23fb11d))


## 0.5.1 (2024-03-05)


### Features
* add macOS socket support and enable macOS CI (#65) ([`4da070d`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/4da070daef1c23be8c3be6e2fb5921b17a23c79a))


## 0.5.0 (2024-02-21)

### BREAKING CHANGES
* add adaptor interface/data versioning (#73) ([`9575aea`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/9575aeac589b70324d5e02c98c6c45dfb2a42fb6))
* show-config is now a command, remove &#34;run&#34; as default, refactor (#74) ([`8030890`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/8030890903b63b9007e00cd3b0ed2487afe990f3))


### Bug Fixes
* fix signal handling (#76) ([`bc38027`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/bc38027a4f572ea802663054fbc07b7164de3037))

## 0.4.2 (2024-02-13)


### Features
* Add the ability for the adaptor to specify its reentry executable (#69) ([`9647ec8`](https://github.com/OpenJobDescription/openjd-adaptor-runtime-for-python/commit/9647ec88b57af6830ca2892e996967bfeaf2eb9c))


