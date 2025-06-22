# Setting up the Pi
=======


[scada-template-2](https://drive.google.com/drive/u/0/folders/1stNbaPS0m_K00DqltmTKjR6WiAvD7Pge) -
This is a 32 GB image that can be loaded onto any >= 32 GB microSD card. It followed this recipe:
 **Started with emonPi 32 GB SD microSD card**

Double-check thatt the SD card is 32 GB(hex screwdriver, open it up).

power it up and use the button to cycle the screen to `enable ssh` and then hold it. Then
look at its address on the LAN (one of the screens) and ssh using username `pi` and password `emonpi2016`

Change ssh password to template password

Change hostname to scada-template-2

sudo nano /etc/hostname

sudo nano /etc/hosts

sudo reboot
 **Various apt-get**

sudo apt-get update

sudo apt-get install -y build-essential tk-dev libncurses5-dev libncursesw5-dev libreadline6-dev libdb5.3-dev libgdbm-dev libsqlite3-dev libssl-dev libbz2-dev libexpat1-dev liblzma-dev zlib1g-dev libffi-dev tar wget vim build-essential libi2c-dev i2c-tools python-dev mosquitto-clients tmux

sudo apt clean


**Python 3.10.4**

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

**Enable interface options**

sudo raspi-config 

Navigate to Interfacing Options, select i2c, and enable it. 
Same for 1-wire

reboot

**Install repo**

Use ssh -A pi@LAN to bring my keys

In /home/pi

mkdir tmp

git clone https://github.com/thegridelectric/gridworks-scada.git

cd gridworks-scada/gw_spaceheat/

python -m venv venv

source venv/bin/activate


export TMPDIR=/home/pi/tmp
mkdir -p $TMPDIR


 /usr/local/bin/pip3.10 install -r requirements/drivers.txt

 resulted in this:
   WARNING: The scripts pyserial-miniterm and pyserial-ports are installed in '/home/pi/.local/bin' which is not on PATH.
  Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location.
  WARNING: The script dotenv is installed in '/home/pi/.local/bin' which is not on PATH.
pip install -r requirements/drivers.txt

**Running the tests**

Activate the virtual environment and install the test requirements: 

    cd gridworks-scada/gw_spaceheat/
    pip install -r requirements/test.txt

Set variables for the tests: 

    export PYTHONPATH=gw_spaceheat
    export GW_SPACEHEAT_TEST_DOTENV_PATH=test/.env-gw-spaceheat-test-pi

Run the tests:

    cd gridworks-scada
    pytest


**Hardware layout file**

Place your hardware layout file at the default path expected by the Scada code. Find that default path with: 

    python -c "import config; print(config.Paths().hardware_layout)"

**Make .env file; Use the local emonPi broker**

Contents of `.env`

```
SCADA_SECONDS_PER_REPORT = 300
SCADA_ASYNC_POWER_REPORTING_THRESHOLD = 0.02
SCADA_LOCAL_MQTT__HOST = "localhost"
SCADA_LOCAL_MQTT__PORT = 1883
SCADA_LOCAL_MQTT__USERNAME = "emonpi"
SCADA_LOCAL_MQTT__PASSWORD = "emonpimqtt2016"
SCADA_GRIDWORKS_MQTT__HOST = "hw1-1.electricity.works"
SCADA_GRIDWORKS_MQTT__PORT = 1883
SCADA_GRIDWORKS_MQTT__USERNAME = "smqPublic"
SCADA_GRIDWORKS_MQTT__PASSWORD = ""


PYTHONPATH=gw_spaceheat
```

**remove `tmp` folder**

cd ~
rm tmp/

**add readme**
From `/home/pi`:

mv readme.md emonpi_orig_readme.md

contents of new `readme.md`:

```
This Pi is designed to run a SCADA  for a residential space heating system
that combines heat pumps with thermal storage and supports the electric grid
by recognizing and utilizing renewable energy when it is available.

The code is open source and available here:
https://github.com/thegridelectric/gridworks-scada

The Pi is also designed to expand on the original functionality of the
emonPi. The SD card started with the image provided in the emonPi sold
by open energy monitor (https://shop.openenergymonitor.com/emonpi/). On
top of that we have installed python 3.10.4 as the default python and
added the repo in this home directory.
```


# WISH LIST FOR NEXT VERSION: 
 - change username and password for the local MQTT broker. Need to make sure that the 
power meter has correct access still.



# MQTT


testing broker access (needs to be on the same LAN as moquitto broker)
mosquitto_sub -v -u emonpi -P emonpimqtt2016 -t 'test'
mosquitto_pub -u emonpi -P emonpimqtt2016 -t 'test' -m 'hi'

mosquitto_sub -v -u emonpi -P emonpimqtt2016 -t 'emon/emonpi/power1'
mosquitto_sub -v -u emonpi -P emonpimqtt2016 -t 'emon/emonpi/vrms'

(see settings.py for username and .env for password)

# hex code for emonpi

With the SD card that ships with the emonPi and the connected atmega, the atmega meter only reports power and voltage every 5 seconds. 

Following the directions [here](https://guide.openenergymonitor.org/technical/compiling/), I added PlatformIo to visual studio code on my mac. I updated the [src.ino](https://github.com/openenergymonitor/emonpi/blob/master/firmware/src/src.ino#L85) c code, changing 5000 to 1000 for TIME_BETWEEN_READINGS. I also changed the bool USA from false to true [here](https://github.com/openenergymonitor/emonpi/blob/master/firmware/src/src.ino#L95) and finally updated the BUILD_TAG in [platformio.ini](https://github.com/openenergymonitor/emonpi/blob/master/firmware/platformio.ini#L30) from 2.9.5 to 2.9.6 (maybe this should be more significant, like gw2.9.5??). The `firmware.hex` built on my mac in the relative directory `emonpi/firmware/.pio/build/emonpi`. 

I scp'd that over to `/opt/openenergymonitor/emonpi/firmware/compiled/latest.hex` on the Pi, and then from that same directory ran `./update`

After doing this, the emonpi meter readings did indeed start going once a second instead of every 5 seconds.

const int TIME_BETWEEN_READINGS=  1000
/opt/openenergymonitor/emonpi/firmware/compiled/update
