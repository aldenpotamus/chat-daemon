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

sys.path.append("..")
from yt_livechat.youtube_livechat import YoutubeLivechat
from auth_manager.auth_manager import AuthManager

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
bannedUserIds = defaultdict(lambda: False)
bannedMsgIds = defaultdict(lambda: False)

twitchProfileCache = {}

discordToWebIdMap = {}

twitchEmoteTemplate = Template('<img class="emote" src=\'https://static-cdn.jtvnw.net/emoticons/v2/${id}/${format}/${theme_mode}/${scale}\'/>')
discordEmoteTemplate = Template('<img class="emote" src=\'https://cdn.discordapp.com/emojis/${id}.webp?size=44&quality=lossless\'/>')
youtubeEmoteTemplate = Template('<img class="emote" alt= \'${alt}\' src=\'${src}\'/>')

# TWITCH
def twitchCallback(data):
    global websocketServer

    if data['display_name'] not in twitchProfileCache.keys():
        for user in twitchDataAPI.users([data['display_name']]):
            print('Got offline profile picture for '+data['display_name'])
            twitchProfileCache[data['display_name']] = user.profile_image_url

    messageWithEmote = twitchEmoteSubs(data['message'],
                                       [e for e in data['event_raw'].split(';') if e.startswith('emotes')][0])

    data['avatarURL'] = twitchProfileCache[data['display_name']]
    (messageId, messageDict) = twitchMsgToJSON(data, messageWithEmote)
    
    if bannedUserIds[messageDict['userId']]:
        print('Banned User: %s [%s] : Ignoring Message' % (messageDict['username'], messageDict['userId']))
    else:
        websocketServer.send_message_to_all(buildMsg('NEW', message=messageDict))
        discordSendMsg(':purple_square: **'+data['display_name']+"**", messageId, messageDict['messageText'])

twitchIdParser = re.compile(r';id=([^;]+)')
def twitchMsgToJSON(msg, msgHTML):
    id = uuid.uuid4().hex
    messageDict = {   
        'id': id,
        'username': msg['display_name'],
        'userId': msg['user_id'],
        'time': msg['event_time'],
        'messageText': msg['message'],
        'messageHTML': msgHTML,
        'service': 'twitch',
        'serviceURL': 'img/twitch_badge_1024.png',
        'eventType': 'ChatMessage',
        'avatarURL': msg['avatarURL'],
        'reactions': [],
        'images': []
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

        for edit in edits:
            msg = twitchEmoteTemplate.safe_substitute({
                'id': edit[1]['id'],
                'format': 'default',
                'theme_mode': 'dark',
                'scale': '3.0'}).join([msg[:edit[1]['start']],msg[(edit[1]['end']+1):]])
    return msg

# YOUTUBE
youtubeAPI = None

def youtubeStart():
    global CONFIG, youtubeVideoId
    bcastService = AuthManager.get_authenticated_service("broadcast",
                                                         clientSecretFile='client_secret.json',
                                                         scopes=["https://www.googleapis.com/auth/youtube.force-ssl"])

    youtubeAPI = YoutubeLivechat(youtubeVideoId,
                                 ytBcastService=bcastService,
                                 callbacks=[youtubeCallback])

    youtubeAPI.start()

def youtubeCallback(message):
    global websocketServer

    messageHTML = youtubeEmoteSubs(message['htmlText'])
    (messageId, messageDict) = youtubeMsgToJSON(message, messageHTML)

    if bannedUserIds[messageDict['userId']]:
        print('Banned User: %s [%s] : Ignoring Message' % (messageDict['username'], messageDict['userId']))
    else:
        websocketServer.send_message_to_all(buildMsg('NEW', message=messageDict))
        discordSendMsg(':red_square: **'+message['authorDetails']['displayName']+'**', messageId, messageDict['messageText'])

def youtubeMsgToJSON(msg, msgHTML):
    id = uuid.uuid4().hex

    messageDict = {
      'id': id,
      'username': msg['authorDetails']['displayName'],
      'userId': msg['authorDetails']['channelId'],
      'time': msg['snippet']['publishedAt'],
      'messageText': msg['snippet']['textMessageDetails']['messageText'],
      'messageHTML': msgHTML,
      'service': 'youtube',
      'serviceURL': 'img/youtube_badge_1024.png',
      'eventType': msg['kind'],
      'avatarURL': msg['authorDetails']['profileImageUrl'],
      'reactions': [],
      'images': []
    }
    messageLog[id] = messageDict
    messageLogOrdered.append(messageDict)
    return (id, messageDict)

def youtubeEmoteSubs(substitutionText):
    msg = ''

    for item in substitutionText:
        if item['type'] == 'text':
            msg += item['text']
        elif item['type'] == 'img':
            msg += youtubeEmoteTemplate.safe_substitute(item)

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

        global youtubeVideoId
        videoDataService = AuthManager.get_authenticated_service("videolist",
                                                                clientSecretFile='client_secret.json',
                                                                scopes=["https://www.googleapis.com/auth/youtube.readonly"])
        videoDataRequest = videoDataService.videos().list(
            part="snippet,contentDetails,statistics",
            id=youtubeVideoId)

        videoDataResponse = videoDataRequest.execute()

        with requests.get(videoDataResponse['items'][0]['snippet']['thumbnails']['standard']['url']) as r:
            img = Image.open(BytesIO(r.content), mode='r', formats=['JPEG'])
            tmpImg = img.crop((0,60,640,420))
            croppedBytes = BytesIO()
            tmpImg.save(croppedBytes, format='PNG')
            croppedBytes.seek(0)

            picture = discord.File(croppedBytes, filename='thumbnail.png', description='YouTube Thumbnail Picture')
            links = 'Going Live Shortly!\n>>> <https://youtu.be/'+youtubeVideoId+'>\n<http://twitch.tv/'+CONFIG['GENERAL']['twitchChannelName']+'>'
            message = await discordChannel.send(content=links, file=picture)

        discordThread = await discordChannel.create_thread(name=videoDataResponse['items'][0]['snippet']['title'] + ' ['+videoDataResponse['items'][0]['snippet']['publishedAt'][0:10]+']',
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
        embeds = []
        
        for embed in message.embeds:
            images.append(get_gif_url(embed.url))
            # images.append((get_gif_url(embed.url, embed.image.)))
            embeds.append(embed.url)

        (id, messageDict) = discordMsgToJSON(message, messageHTML, images)
        discordToWebIdMap[message.id] = id
        
        # strip embeds from message
        print('MESSAGE: %s', messageDict)
        print('EMBEDS:  %s', embeds)

        for embed in embeds:
            messageDict['messageText'] = messageDict['messageText'].replace(embed, '')
            messageDict['messageHTML'] = messageDict['messageHTML'].replace(embed, '')

        if bannedUserIds[messageDict['userId']]:
            print('Banned User: %s [%s] : Ignoring Message' % (messageDict['username'], messageDict['userId']))
        else:
            websocketServer.send_message_to_all(buildMsg('NEW', message=messageDict))

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

        websocketServer.send_message_to_all(buildMsg('SHOW', ids=[messageId], message=messageLog[messageId]))

        if reaction.emoji.id:
            reactionImage = discordEmoteTemplate.safe_substitute({'id': reaction.emoji.id, 'class': 'customReaction'})
            reactionHTML = reactionImage
        else:
            reactionHTML = reaction.emoji.name
        websocketServer.send_message_to_all(buildMsg('REACT', ids=[messageId], message=messageLog[messageId], reactionHTML=reactionHTML))
        messageLog[messageId]['reactions'].append(reactionHTML)

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
      'username': msg.author.name,
      'userId': msg.author.id, 
      'time': msg.id,
      'messageText': msg.content,
      'messageHTML': msgHTML,
      'service': 'discord',
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

def buildMsg(action, id=None, ids=None, message=None, messages=None, username=None, reactionHTML=None):   
    return json.dumps({
        'action': action,
        'payload': {
            'id': str(message['id']) if message else id,
            'ids': ids,
            'username': str(message['username']) if message else username,
            'message': message,
            'messages': messages,
            'reactionHMTL': reactionHTML
        }
    })

def clientMessage(client, server, msgStr):
    message = json.loads(msgStr)
    
    action = message['action']
    payload = message['payload']

    match action:
        case 'HIDE':
            print('Hiding Message: %s' % payload)
            hiddenIds[payload['id']] = True
            websocketServer.send_message_to_all(buildMsg('HIDE', id=payload['id'], message=messageLog[payload['id']]))
            return
        case 'SHOW':
            print('Showing Message: %s' % payload)

            hiddenIds[payload['id']] = False
            websocketServer.send_message_to_all(buildMsg('NEW', id=payload['id'], message=messageLog[payload['id']]))
            websocketServer.send_message_to_all(buildMsg('SHOW', id=payload['id'], message=messageLog[payload['id']]))
            if pinnedIds[payload['id']]:
                websocketServer.send_message_to_all(buildMsg('PIN', id=payload['id'], message=messageLog[payload['id']]))
            return
        case 'PIN':
            print('Pin Message: %s' % payload)
            pinnedIds[payload['id']] = True
            hiddenIds[payload['id']] = False
            websocketServer.send_message_to_all(buildMsg('NEW', id=payload['id'], message=messageLog[payload['id']]))
            websocketServer.send_message_to_all(buildMsg('SHOW', id=payload['id'], message=messageLog[payload['id']]))
            websocketServer.send_message_to_all(buildMsg('PIN', id=payload['id'], message=messageLog[payload['id']]))
            pinnedIds
            return
        case 'UNPIN':
            print('Unpin Message: %s' % payload)
            pinnedIds[payload['id']] = False
            websocketServer.send_message_to_all(buildMsg('UNPIN', id=payload['id'], message=messageLog[payload['id']]))
            return
        case 'BAN':
            print('Ban Message: %s' % payload)
            userIdToBan = messageLog[payload['id']]['userId']
            bannedUserIds[userIdToBan] = True

            for messageToBan in [m for m in messageLogOrdered if m['userId'] == userIdToBan]:
                websocketServer.send_message_to_all(buildMsg('BAN', id=messageToBan['id']))

            return
        case 'UNBAN':
            print('Unban Message: %s' % payload)
            userIdToUnban = messageLog[payload['id']]['userId']
            bannedUserIds[userIdToUnban] = False

            for messageToUnban in [m for m in messageLogOrdered if m['userId'] == userIdToUnban]:
                websocketServer.send_message_to_all(buildMsg('UNBAN', id=messageToUnban['id']))

            return
        case 'CLEAR':
            print('Clearing Clients')
            websocketServer.send_message_to_all(buildMsg('CLEAR'))
            return
        case 'RELOAD':
            print('Reloading Clients')
            if payload['args']:
                numMessages = payload['args'][0]
            else:
                numMessages = 0
            
            websocketServer.send_message_to_all(buildMsg('RELOAD', messages=messageLogOrdered[-numMessages:]))
            for message in messageLogOrdered[-numMessages:]:
                if pinnedIds[message['id']]:
                    websocketServer.send_message_to_all(buildMsg('PIN', id=message['id'], message=messageLog[message['id']]))
                if hiddenIds[message['id']]:
                    websocketServer.send_message_to_all(buildMsg('HIDE', id=message['id'], message=messageLog[message['id']]))
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
    youtubeStart()

if __name__ == '__main__':
    print('Running for video: '+str(sys.argv[1]))
    youtubeVideoId = str(sys.argv[1])
    del sys.argv[1]

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
