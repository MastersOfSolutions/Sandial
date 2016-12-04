## Source Code Root of C Implementation

### Adding External libs
```bash
cd /PATH/TO/SANDIAL/REPO/ROOT
```
```bash
mkdir ./external && cd ./external
git clone git://git.drogon.net/wiringPi
cd ./wiringPi
./build
```

> NOTE: The ./build is expected to fail if not on RPi

