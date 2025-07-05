# chat-daemon
Display multiple livestream chat-feeds (and more) in OBS entirely locally hosted.

## Requirements
pip install aiohttp
pip install pygsheets
pip install -U py-cord
pip install -U pytz
pip install websocket_server
pip install Pillow
pip install pytchat
pip install twitchio
pip install python-youtube

## Installation
Download the project via git:
```
git clone git@github.com:aldenpotamus/chat-daemon.git
```

Pull dependant projects with pip:
```
pip install -r requirements.txt
```

https://twitchapps.com/tmi/

## Authentication
Step 1
---
Copy example.ini, rename it config.ini and add your respective tokens.  More on this in the future.

Step 2
---
...

## Usage
Run the following command:
```
python chat_daemon <youtube video id>
```