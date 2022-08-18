import asyncio
import configparser
from email.errors import MessageError
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
# from ..pytchat import pytchat
import requests
import twitch
from PIL import Image
from pytchat import LiveChatAsync
from pywitch import PyWitchTMI
from pyyoutube import Api
from websocket_server import WebsocketServer
import re

disableDiscordThread = True
testThread = 998310893387534367

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

discordToWebIdMap = {}

twitchEmoteTemplate = Template('<img src=\'https://static-cdn.jtvnw.net/emoticons/v2/${id}/${format}/${theme_mode}/${scale}\'/>')
discordEmoteTemplate = Template('<img class=\'${class}\' src=\'https://cdn.discordapp.com/emojis/${id}.webp?size=44&quality=lossless\'/>')
youtubeEmoteTemplate = Template('<img src=\'${imgURL}\'/>')

# TWITCH
def twitchCallback(data):
    global websocketServer
    print(data)

    if data['display_name'] not in twitchProfileCache.keys():
        for user in twitchDataAPI.users([data['display_name']]):
            print('Got offline profile picture for '+data['display_name'])
            twitchProfileCache[data['display_name']] = user.profile_image_url

    messageWithEmote = twitchEmoteSubs(data['message'],
                                       [e for e in data['event_raw'].split(';') if e.startswith('emotes')][0])

    data['avatarURL'] = twitchProfileCache[data['display_name']]
    (messageId, messageDict) = twitchMsgToJSON(data, messageWithEmote)
    websocketServer.send_message_to_all('MSG|'+json.dumps(messageDict))
    discordSendMsg(':purple_square: **'+data['display_name']+"**", messageId, data['message'])

twitchIdParser = re.compile(r';id=([^;]+)')
def twitchMsgToJSON(msg, msgHTML):
    id = uuid.uuid4().hex
    messageDict = {   
        'id': id,
        'userName': msg['display_name'],
        'time': msg['event_time'],
        'messageText': msg['message'],
        'messageHTML': msgHTML,
        'service': 'Twitch',
        'serviceURL': 'img/twitch_badge_1024.png',
        'eventType': 'ChatMessage',
        'avatarURL': msg['avatarURL'],
        'reactions': []
    }
    messageLog[id] = messageDict
    messageLogOrdered.append(messageDict)
    return (id, messageDict)

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

async def youtubeCallback(dataList):
    global websocketServer
    for data in dataList.items:
        print(str(data))
        messageHTML = youtubeEmoteSubs(data.messageEx)
        (messageId, messageDict) = youtubeMsgToJSON(data, messageHTML)
        websocketServer.send_message_to_all('MSG|'+json.dumps(messageDict))
        discordSendMsg(':red_square: **'+data.author.name+'**', messageId, data.message)

def youtubeMsgToJSON(msg, msgHTML):
    id = uuid.uuid4().hex
    messageDict = {
      'id': id,
      'userName': msg.author.name,
      'time': msg.timestamp,
      'messageText': msg.message,
      'messageHTML': msgHTML,
      'service': 'YouTube',
      'serviceURL': 'img/youtube_badge_1024.png',
      'eventType': msg.type,
      'avatarURL': msg.author.imageUrl,
      'reactions': []
    }
    messageLog[id] = messageDict
    messageLogOrdered.append(messageDict)
    return (id, messageDict)

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
    
    global discordThread
    if disableDiscordThread:
        discordChannel = discordClient.get_channel(testThread) #Test Channel
        discordThread = discordClient.get_channel(testThread) #Test Channel
    else:
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

        discordThread = await discordChannel.create_thread(name=videoData.items[0].snippet.title+' ['+videoData.items[0].snippet.publishedAt[0:10]+']',
                                                        message=message,
                                                        auto_archive_duration=1440)
        print('1 Thread: '+str(discordThread))

@discordClient.event
async def on_message(message):
    global discordThread
    if not message.author.bot and message.channel.id == discordThread.id:
        print('[DISCORD] Message: '+str(message))
        messageHTML = discordEmoteSubs(message.clean_content)
        
        images = [image.url for image in message.attachments + message.stickers]
        for embed in message.embeds:
            images.append(get_gif_url(embed.url))

        (id, messageDict) = discordMsgToJSON(message, messageHTML, images)
        discordToWebIdMap[message.id] = id
        websocketServer.send_message_to_all('MSG|'+json.dumps(messageDict))
        if len(images) > 0:
            websocketServer.send_message_to_all('HIDE|'+id)

def get_gif_url(view_url):
    # Get the page content
    page_content = requests.get(view_url).text

    # Regex to find the URL on the c.tenor.com domain that ends with .gif
    regex = r"(?i)\b((https?://c[.]tenor[.]com/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))[.]gif)"

    # Find and return the first match
    return re.findall(regex, page_content)[0][0]

@discordClient.event
async def on_raw_reaction_add(reaction):
    global discordThread
    if reaction.channel_id == discordThread.id:
        print('[DISCORD] Reaction: '+str(reaction))
        
        messageId = reaction.message_id
        if messageId in discordToWebIdMap.keys():
            messageId = discordToWebIdMap[messageId]

        websocketServer.send_message_to_all('MSG|'+json.dumps(messageLog[messageId]))
        websocketServer.send_message_to_all('UNHIDE|'+messageId)
        if reaction.emoji.id:
            reactionImage = discordEmoteTemplate.safe_substitute({'id': reaction.emoji.id, 'class': 'customReaction'})
            reactionInnerHTML = reactionImage
        else:
            reactionInnerHTML = reaction.emoji.name
        websocketServer.send_message_to_all('REACTION|'+reactionInnerHTML+"@"+str(messageId))
        messageLog[messageId]['reactions'].append(reactionInnerHTML)

async def waitAndSendDiscordMessage(message, webMsgId):
    global discordThread
    message = await discordThread.send(message)
    discordToWebIdMap[message.id] = webMsgId 

def discordSendMsg(user, webMsgId, message):
    print('Requesting Send:' +message)
    asyncio.run_coroutine_threadsafe(waitAndSendDiscordMessage(user+": "+message, webMsgId), loop=discordClient.loop)

def discordMsgToJSON(msg, msgHTML, images=None):
    id = uuid.uuid4().hex
    messageDict = {
      'id': id,
      'userName': msg.author.name,
      'time': msg.id,
      'messageText': msg.content,
      'messageHTML': msgHTML,
      'service': 'Discord',
      'serviceURL': 'img/discord_badge_1024.png',
      'eventType': msg.type,
      'avatarURL': './img/blank_profile_pic.png' if  msg.author.avatar is None else msg.author.avatar.url,
      'reactions': [],
      'images': images
    }
    messageLog[id] = messageDict
    messageLogOrdered.append(messageDict)
    return (id, messageDict)

discordEmotePattern = re.compile(r'<:[^:]*:([0-9]+)>')
def discordEmoteSubs(messageText):
    return discordEmotePattern.sub(discordEmoteTemplate.safe_substitute({'id': r'\1'}), messageText)

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
            websocketServer.send_message_to_all('MSG|'+json.dumps(messageLog[param]))
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
            websocketServer.send_message_to_all('MSG|'+json.dumps(messageLog[param]))
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
    messagesStr = json.dumps(messages)

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
