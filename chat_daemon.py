import asyncio
import configparser
import http.server
import json
import logging
import socketserver
import sys
import threading
import uuid
from collections import defaultdict
from io import BytesIO
from os.path import exists
from string import Template

import discord
import pytchat
import requests
import twitch
from PIL import Image
from pytchat import LiveChatAsync
from pywitch import PyWitchTMI
from pyyoutube import Api
from websocket_server import WebsocketServer

logger = logging.getLogger('discord')
logger.setLevel(logging.ERROR)

global youtubeVideoId, discordThread
youtubeVideoId = None
discordThread = None

messageLog = {}
messageLogOrdered = []
pinnedIds = defaultdict(lambda: False)
hiddenIds = defaultdict(lambda: False)
twitchProfileCache = {}

messageTemplate = Template('''{
    "id": "${id}",
    "userName": "${userName}",
    "time": "${time}",
    "messageText": ${messageText},
    "messageHTML": ${messageHTML},
    "service": "${service}",
    "serviceURL": "${serviceURL}",
    "eventType": "${eventType}",
    "avatarURL": "${avatarURL}"
}''')
twitchEmoteTemplate = Template('<img src=\'https://static-cdn.jtvnw.net/emoticons/v2/${id}/${format}/${theme_mode}/${scale}\'/>')
youtubeEmoteTemplate = Template('<img src=\'${imgURL}\'/>')

# TWITCH
def twitchCallback(data):
    global websocketServer
    print('TWITCH')
    print(data)
    if data['display_name'] not in twitchProfileCache.keys():
        for user in twitchDataAPI.users([data['display_name']]):
            print('Got offline profile picture for '+data['display_name'])
            print(user.profile_image_url)
            twitchProfileCache[data['display_name']] = user.profile_image_url

    messageWithEmote = twitchEmoteSubs(data['message'],
                                       [e for e in data['event_raw'].split(';') if e.startswith('emotes')][0])
    print(messageWithEmote)

    data['avatarURL'] = twitchProfileCache[data['display_name']]
    websocketServer.send_message_to_all('MSG|'+twitchMsgToJSON(data, messageWithEmote))
    discordSendMsg(':purple_square: **'+data['display_name']+"**", "Twitch", data['message'])

def twitchMsgToJSON(msg, msgHTML):
    id = uuid.uuid4().hex
    message = messageTemplate.safe_substitute({
      'id': id,
      'userName': msg['display_name'],
      'time': msg['event_time'],
      'messageText': json.dumps(msg['message']),
      'messageHTML': json.dumps(msgHTML),
      'service': 'Twitch',
      'serviceURL': 'img/twitch_badge_1024.png',
      'eventType': 'ChatMessage',
      'avatarURL': msg['avatarURL']
    })
    messageLog[id] = message
    messageLogOrdered.append(message)
    return message

def twitchEmoteSubs(messageText, substitutionText):
    msg = messageText
    edits = []

    if len(substitutionText[7:]) > 1:
        for emote in substitutionText[7:].split('/'):
            id, ranges = emote.split(':')
            for range in ranges.split(','):
                start, end = range.split('-')
                start = int(start)
                end = int(end)
                edits.append((end, {'id': id, 'start': start, 'end': end}))
        edits.sort(key=lambda x: x[0], reverse=True)

        print(edits)

        for edit in edits:
            msg = twitchEmoteTemplate.safe_substitute({
                'id': edit[1]['id'],
                'format': 'default',
                'theme_mode': 'dark',
                'scale': '3.0'}).join([msg[:edit[1]['start']],msg[(edit[1]['end']+1):]])
    return msg

# YOUTUBE
youtubeAPI = None

async def youtubeStart():
    global CONFIG, youtubeAPI, youtubeVideoId
    youtubeAPI = Api(api_key=CONFIG['AUTHENTICATION']['youtubeApiKey'])
    livechat = LiveChatAsync(youtubeVideoId, callback=youtubeCallback)
    while True:
        await asyncio.sleep(1)

    try:
        livechat.raise_for_status()
    except pytchat.ChatDataFinished:
        print("Chat data finished.")
    except Exception as e:
        print(type(e), str(e))

async def  youtubeCallback(dataList):
    global websocketServer
    for data in dataList.items:
        print(str(data))
        messageHTML = youtubeEmoteSubs(data.messageEx)
        websocketServer.send_message_to_all('MSG|'+youtubeMsgToJSON(data,messageHTML))
        discordSendMsg(':red_square: **'+data.author.name+'**', "YouTube", data.message)

def youtubeMsgToJSON(msg, msgHTML):
    id = uuid.uuid4().hex
    message = messageTemplate.safe_substitute({
      'id': id,
      'userName': msg.author.name,
      'time': msg.timestamp,
      'messageText': json.dumps(msg.message),
      'messageHTML': json.dumps(msgHTML),
      'service': 'YouTube',
      'serviceURL': 'img/youtube_badge_1024.png',
      'eventType': msg.type,
      'avatarURL': msg.author.imageUrl
    })
    messageLog[id] = message
    messageLogOrdered.append(message)
    return message

def youtubeEmoteSubs(substitutionText):
    msg = ''

    for item in substitutionText:
        if isinstance(item, str):
            msg += item
        else:
            msg += youtubeEmoteTemplate.safe_substitute({'imgURL': item['url']})

    return msg

# DISCORD
discordIntents = discord.Intents.default()
discordIntents.members = True
discordIntents.presences = True
discordIntents.message_content = True
discordClient = discord.Client(intents=discordIntents)

def discordClientThreadTarget():
    global CONFIG
    discordClient.run(CONFIG['AUTHENTICATION']['discordToken'])

@discordClient.event
async def on_ready():
    global CONFIG
    print('[DISCORD] We have logged in as {0.user}'.format(discordClient))
    discordChannel = discordClient.get_channel(965324208362111076)

    global youtubeAPI, youtubeVideoId
    videoData = youtubeAPI.get_video_by_id(video_id=youtubeVideoId)
    with requests.get(videoData.items[0].snippet.thumbnails.standard.url) as r:
        img = Image.open(BytesIO(r.content), mode='r', formats=['JPEG'])
        tmpImg = img.crop((0,60,640,420))
        croppedBytes = BytesIO()
        tmpImg.save(croppedBytes, format='PNG')
        croppedBytes.seek(0)

        picture = discord.File(croppedBytes, filename='thumbnail.png', description='YouTube Thumbnail Picture')
        links = 'Going Live Shortly!\n>>> <https://youtu.be/'+youtubeVideoId+'>\n<http://twitch.tv/'+CONFIG['GENERAL']['twitchChannelName']+'>'
        message = await discordChannel.send(content=links, file=picture)

    global discordThread
    discordThread = await discordChannel.create_thread(name=videoData.items[0].snippet.title+' ['+videoData.items[0].snippet.publishedAt[0:10]+']',
                                                       message=message,
                                                       auto_archive_duration=1440)
    print('1 Thread: '+str(discordThread))

@discordClient.event
async def on_message(message):
    global discordThread
    print('[DISCORD] Message: '+str(message))
    if not message.author.bot and message.channel.id == discordThread.id:
        websocketServer.send_message_to_all('MSG|'+discordMsgToJSON(message, message.clean_content))

async def waitAndSendDiscordMessage(message):
    global discordThread
    await discordThread.send(message)

def discordSendMsg(user, service, message):
    print('Requesting Send:' +message)
    asyncio.run_coroutine_threadsafe(waitAndSendDiscordMessage(user+": "+message), loop=discordClient.loop)

def discordMsgToJSON(msg, msgHTML):
    id = uuid.uuid4().hex
    message = messageTemplate.safe_substitute({
      'id': id,
      'userName': msg.author.name,
      'time': msg.id,
      'messageText': json.dumps(msg.content),
      'messageHTML': json.dumps(msg.clean_content),
      'service': 'Discord',
      'serviceURL': 'img/discord_badge_1024.png',
      'eventType': msg.type,
      'avatarURL': msg.author.avatar.url
    })
    messageLog[id] = message
    messageLogOrdered.append(message)
    return message

# WEBSOCKETS
def clientJoin(client, server):
	print("New client connected and was given id %d" % client['id'])

def clientDisconnect(client, server):
	print("Client(%d) disconnected" % client['id'])

def clientMessage(client, server, message):
    action = message.split('|')[0]
    param = message.split('|')[1]

    print(message)
    match action:
        case 'DUMMY':
            print('Sending Dummy Message to Clients')
            if param in dummyMessages.keys():
                websocketServer.send_message_to_all('DUMMY|'+dummyMessages[param])
            else:
                print(param+' not yet implemented.')
            return
        case 'PIN':
            print('Pin Message: '+param)
            pinnedIds[param] = True
            hiddenIds[param] = False
            websocketServer.send_message_to_all('MSG|'+messageLog[param])
            websocketServer.send_message_to_all('UNHIDE|'+param)
            websocketServer.send_message_to_all('PIN|'+param)
            return
        case 'UNPIN':
            print('Unpin Message: '+param)
            pinnedIds[param] = False
            websocketServer.send_message_to_all('UNPIN|'+param)
            return
        case 'HIDE':
            print('Hiding Message: '+param)
            hiddenIds[param] = True
            websocketServer.send_message_to_all('HIDE|'+param)
            return
        case 'UNHIDE':
            print('Showing Message: '+param)
            hiddenIds[param] = False
            websocketServer.send_message_to_all('MSG|'+messageLog[param])
            websocketServer.send_message_to_all('UNHIDE|'+param)
            if pinnedIds[param]:
                websocketServer.send_message_to_all('PIN|'+param)
            return
        case 'CLEAR':
            print('Clearing all clients.')
            websocketServer.send_message_to_all('CLEAR|')
            return
        case 'RELOAD_CLIENTS':
            print('Clearing all clients.')
            websocketServer.send_message_to_all('CLEAR|')

            print('Reloading '+param+' messages on ALL clients.')
            messagesStr = processMessage(param)
            websocketServer.send_message_to_all('RELOAD|'+messagesStr)

            print('Repinning all pinned messages on all clients.')
            for messageid in pinnedIds.keys():
                if pinnedIds[messageid]:
                    print('Pinning message: '+messageid)
                    websocketServer.send_message_to_all('PIN|'+messageid)

            print('Hiding all hidden messages on all clients.')
            for messageid in hiddenIds.keys():
                if hiddenIds[messageid]:
                    print('Hiding message: '+messageid)
                    websocketServer.send_message_to_all('HIDE|'+messageid)
            return
        case 'RELOAD':
            print('Reloading '+param+' messages')
            messagesStr = processMessage(param)
            websocketServer.send_message(client, 'RELOAD|'+messagesStr)

            print('Repinning all pinned messages on all clients.')
            for messageid in pinnedIds.keys():
                if pinnedIds[messageid]:
                    print('Pinning message: '+messageid)
                    websocketServer.send_message(client, 'PIN|'+messageid)

            print('Hiding all hidden messages on all clients.')
            for messageid in hiddenIds.keys():
                if hiddenIds[messageid]:
                    print('Hiding message: '+messageid)
                    websocketServer.send_message(client, 'HIDE|'+messageid)
            return
        case _:
            print("Unrecognized command from client: "+action)

def processMessage(numMessagesStr):
    if numMessagesStr == 'ALL':
        messages = messageLogOrdered.copy()
    else:
        messages = messageLogOrdered[-int(numMessagesStr):]

    messages.reverse()
    messagesStr = '['
    for m in messages:
        messagesStr +=m+','
    messagesStr = messagesStr[:-1]+']'

    return messagesStr

def httpServerThreadTarget():
    Handler = http.server.SimpleHTTPRequestHandler

    global CONFIG
    with socketserver.TCPServer(("", int(CONFIG['SERVER']['httpServerPort'])), Handler) as httpd:
        print("httpServer started on port:", CONFIG['SERVER']['httpServerPort'])
        httpd.serve_forever()

def main():
    global CONFIG
    print("HTTP Server Thread Starting...")
    httpServerThread = threading.Thread(target=httpServerThreadTarget,
                                        daemon=True)
    httpServerThread.start()

    print("Connecting to Twitch...")
    twitchChat = PyWitchTMI(
        channel = CONFIG['AUTHENTICATION']['twitchChannelName'],
        token = CONFIG['AUTHENTICATION']['twitchToken'],
        callback = twitchCallback,  # Optional
        users = {},                 # Optional, but strongly recomended
        verbose = True,             # Optional
    )
    twitchChat.start()
    global twitchDataAPI
    twitchDataAPI = twitch.Helix(CONFIG['AUTHENTICATION']['twitchClientID'],
                                 CONFIG['AUTHENTICATION']['twitchClientSecret'])

    print("WebSocket Server Starting...")
    global websocketServer
    websocketServer = WebsocketServer(port=int(CONFIG['SERVER']['socketServerPort']), host='0.0.0.0')
    websocketServer.set_fn_new_client(clientJoin)
    websocketServer.set_fn_client_left(clientDisconnect)
    websocketServer.set_fn_message_received(clientMessage)
    websocketServer.run_forever(True)

    print('Connecting to Discord')
    discordClientThread = threading.Thread(target=discordClientThreadTarget, daemon=True)
    discordClientThread.start()

    print("Connecting to YouTube...")
    try:
        asyncio.run(youtubeStart())
    except asyncio.exceptions.CancelledError:
        pass

if __name__ == '__main__':
    print('Running for video: '+str(sys.argv[1]))
    youtubeVideoId = str(sys.argv[1])

    print('Parsing config file...')
    CONFIG = configparser.ConfigParser()
    CONFIG.read('config.ini')

    global dummyMessages
    if(exists(CONFIG['GENERAL']['dummyMessageFile'])):
        print('Loading dummy messages...')
        with open('dummy_messages.json', 'r') as file:
            dummyMessages = json.load(file)
    else:
        print('No dummy file found, use dummyMessageBuilder.py to create one, if needed.')
        dummyMessages = {}

    print('Running chatDaemon...')
    print('Args: '+str(sys.argv))
    main()
