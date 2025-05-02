This template is a transitional raspberry Pi OS as we upgrade to a 64 bit architecture and python 3.12.


# Tests for success
**mosquitto**


```
sudo systemctl status mosquitto 
```
to see that the broker is running on the pi

Pull up two different shells and then:
```
mosquitto_sub -h localhost -p 1883 -u sara -P [LOOK UP MOSQUITTO IN 1PASSWORD] -t foo
```

```
mosquitto_pub -h localhost -u sara -P [LOOK UP MOSQUITTO IN 1PASSWORD] -t foo -m "hi"
```

**warning** The SCADA repos (gridworks-scada, starter-scripts) are installed in the home directory but the packages have not been added so the code won't work yet. Going through a housecleaning
process for this (e.g. removing the pendulum package from the gridworks package as the pendulum team is small enough that it did not keep pendulum up to date with python 3.12 on a 32 bit architecture.)


# Recipe for scada-template-5


- Download [2024-03-15-raspios-bookworm-arm64.img.xz](https://www.raspberrypi.com/software/operating-systems/#raspberry-pi-os-64-bit) from the Raspberry Pi foundation
- xz -d 2024-03-15-raspios-bookworm-arm64.img.xz
- Load onto a 32 GB SD card using balena etcher
- connected a mouse, keyboard and screen to a Pi 4, stuck in SD card
- sudo apt-get --purge remove libreoffice*
- added ssh (sudo apt-get update; sudo apt-get upgrade; sudo apt-get install openssh-client)
- change name to scada-template-64-0  (sudo nano /etc/hosts; sudo nano /etc/hostname)
- verified that ssh'ing worked
- Used the mac Disk Utility to burn an image
  - click on "view all devices" to see the 32 GB SD Card
  - Drop down file, pick DVD/CD master for format
  - change from `.cdr` to `.iso` 


**Python 3.12.4, mosquitto broker, tmux**


sudo apt-get update

```
sudo apt-get install -y build-essential tk-dev libncurses5-dev 
sudo apt-get install -y libncursesw5-dev libreadline-dev libdb5.3-dev libgdbm-dev libsqlite3-dev 
sudo apt-get install -y libssl-dev libbz2-dev libexpat1-dev liblzma-dev zlib1g-dev libffi-dev xz-utils 
sudo apt-get install -y tar wget vim build-essential libi2c-dev curl llvm  i2c-tools 
sudo apt-get install -y mosquitto-clients libnss3-dev mosquitto mosquitto-clients

So that the hostname shows up via multicast dns (e.g. fir2.local):
sudo apt install avahi-daemon

sudo apt clean

curl https://pyenv.run | bash
```

Added to .bashrc:
```
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
```

Then
```
pyenv install 3.12.4
pyenv global 3.12.4
```


**mosquitto broker and cli clients**
- sudo systemctl enable mosquitto.service
 - sudo mosquitto_passwd -c /etc/mosquitto/passwd sara  
 - and then enter password (in 1password)
 - sudo nano /etc/mosquitto/mosquitto.conf
   - First line:
   ```per_listener_settings true```
   - At the end:
   ```
    allow_anonymous false
    listener 1883
    password_file /etc/mosquitto/passwd
   ```

**tmux**
  ```
  sudo apt update
  sudo apt install tmux
  ```


**Enable interface options**

sudo raspi-config 

Navigate to Interfacing Options, select i2c, and enable it. 
Same for 1-wire

reboot

**Install repos**

Use ssh -A pi@LAN to bring my keys

In /home/pi

```
git@github.com:thegridelectric/gridworks-scada.git
git clone git@github.com:thegridelectric/starter-scripts.git
```

**Update .bashrc and other home directory scripts**

Add gw and st as alias commands to go to the scada and starter-scripts repos respectively