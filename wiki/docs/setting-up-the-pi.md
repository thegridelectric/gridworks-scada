# Setting up the Pi
=======

Use a Pi 4 B. 

For the Maine project we used Pi 4Bs with 2 GB of ram  and 16 GB Micro Ultra sandisk 98 NB.s speed class 10 SD cards.

The scada pi was choking on sudo apt-get update 
(This must be accepted explicitly before updates for this repository can be applied. See apt-secure(8) manpage for details)

This worked:
sudo apt-get update --allow-releaseinfo-change

# apt-get libraries 

followed these instructions:
https://installvirtual.com/how-to-install-python-3-8-on-raspberry-pi-raspbian/
and adding moquitto-clients

sudo apt-get update

sudo apt-get install -y build-essential tk-dev libncurses5-dev libncursesw5-dev libreadline6-dev libdb5.3-dev libgdbm-dev libsqlite3-dev libssl-dev libbz2-dev libexpat1-dev liblzma-dev zlib1g-dev libffi-dev tar wget vim build-essential libi2c-dev i2c-tools python-dev mosquitto-clients

sudo apt clean

# python

wget https://www.python.org/ftp/python/3.10.4/Python-3.10.4.tgz

sudo tar zxf Python-3.10.4.tgz
cd Python-3.10.4
sudo ./configure --enable-optimizations
sudo make -j 4
sudo make altinstall


echo "alias python=/usr/local/bin/python3.10" >> ~/.bashrc
source ~/.bashrc

python -V

sudo rm -rf Python-3.10.4.tgz
sudo rm -rf Python-3.10.4


Follow directions from readme. HOWEVER, 
AFTER going into the venv and BEFORE doing pip install:

export TMPDIR=/home/pi/tmp


regular pip was going to /usr/bin/pip and failing. Did this:
 /usr/local/bin/pip3.10 install -r requirements/drivers.txt

 resulted in this:
   WARNING: The scripts pyserial-miniterm and pyserial-ports are installed in '/home/pi/.local/bin' which is not on PATH.
  Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location.
  WARNING: The script dotenv is installed in '/home/pi/.local/bin' which is not on PATH.

But seems to work.

# Raspberry Pi i2c 

The first time I tried to use i2c, it was to control an [ncd_pr8-14 relay](https://docs.google.com/document/d/1DurCUDddqoAkloZs7OPQh909biuquTCC3XDcZe132yg/edit)


(See learning/by_function/ncd_pr-8-14_spst for example scripts)


After loading the various drivers, I tried to run the simple-gpio-monitor script and got this error:
 No such file or directory: '/dev/i2c-1'


[Devine Lu Linvega](https://github.com/neauoire) of [100 rabbits](http://100r.co/site/about_us.html) points out [here](https://github.com/pimoroni/inky-phat/issues/28) that the pi interface needs to be activated, first by typing sudo raspi-config and then
navigating to Interfacing Options, selecting i2c, and enabling it. Alternatively,
sudo nano /boot/config.txt and make sure it has the a line with dtparam=i2c_arm=on

# MQTT



testing broker access (needs to be on the same LAN as moquitto broker)
mosquitto_sub -v -u emonpi -P emonpimqtt2016 -t 'test'
mosquitto_pub -u emonpi -P emonpimqtt2016 -t 'test' -m 'hi'

mosquitto_sub -v -u emonpi -P emonpimqtt2016 -t 'emon/emonpi/power1'
mosquitto_sub -v -u emonpi -P emonpimqtt2016 -t 'emon/emonpi/vrms'

(see settings.py for username and .env for password)

# 1-wire
Followed these instructions (https://learn.adafruit.com/adafruits-raspberry-pi-lesson-11-ds18b20-temperature-sensing?view=all)

sudo raspi-config, 5) Interface Options P7) 1-Wire, Select yes
sudo reboot

lsmod | grep -i w1_

look for 
w1_therm   
w1_gpio
wire

# hex code for emonpi

With the SD card that ships with the emonPi and the connected atmega, the atmega meter only reports power and voltage every 5 seconds. 

Following the directions [here](https://guide.openenergymonitor.org/technical/compiling/), I added PlatformIo to visual studio code on my mac. I updated the [src.ino](https://github.com/openenergymonitor/emonpi/blob/master/firmware/src/src.ino#L85) c code, changing 5000 to 1000 for TIME_BETWEEN_READINGS. I also changed the bool USA from false to true [here](https://github.com/openenergymonitor/emonpi/blob/master/firmware/src/src.ino#L95) and finally updated the BUILD_TAG in [platformio.ini](https://github.com/openenergymonitor/emonpi/blob/master/firmware/platformio.ini#L30) from 2.9.5 to 2.9.6 (maybe this should be more significant, like gw2.9.5??). The `firmware.hex` built on my mac in the relative directory `emonpi/firmware/.pio/build/emonpi`. 

I scp'd that over to `/opt/openenergymonitor/emonpi/firmware/compiled/latest.hex` on the Pi, and then from that same directory ran `./update`

After doing this, the emonpi meter readings did indeed start going once a second instead of every 5 seconds.

const int TIME_BETWEEN_READINGS=  1000
/opt/openenergymonitor/emonpi/firmware/compiled/update