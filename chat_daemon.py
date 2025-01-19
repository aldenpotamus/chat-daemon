import asyncio
import aiohttp
import configparser
import html
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
import time
import pygsheets

import discord

sys.path.append("..")
from yt_livechat.youtube_livechat import YoutubeLivechat
from auth_manager.auth_manager import AuthManager
from kick_livechat.kick_livechat import KickLivechat

import requests
from PIL import Image
from pytchat import LiveChatAsync

import twitchio
from twitchio.ext import commands

from pyyoutube import Api
from websocket_server import WebsocketServer
import re

discordThread = None
currentDiscordThreadId = None
youtubeVideoIds = None

logger = logging.getLogger('discord')
logger.setLevel(logging.ERROR)

messageLog = {}
messageLogOrdered = []
activeUsers = {}

pinnedIds = defaultdict(lambda: False)
hiddenIds = defaultdict(lambda: False)
bannedUserIds = defaultdict(lambda: False)
bannedMsgIds = defaultdict(lambda: False)

twitchProfileCache = {}

discordToWebIdMap = {}

twitchEmoteTemplate = Template('<img class="emote" src=\'https://static-cdn.jtvnw.net/emoticons/v2/${id}/${format}/${theme_mode}/${scale}\'/>')
bttvEmoteTemplate = Template('<img class="emote" src=\'https://cdn.betterttv.net/emote/${id}/3x.${imageType}\'/>')
discordEmoteTemplate = Template('<img class="emote" src=\'https://cdn.discordapp.com/emojis/${id}.webp?size=44&quality=lossless\'/>')
youtubeEmoteTemplate = Template('<img class="emote" alt= \'${text}\' src=\'${src}\'/>')

# CHATBOT
atMentionRegex = r'@([A-Za-z0-9_]+)'
def checkAtMention(messageText):
    print(f'ACTIVE: {activeUsers}')
    mentionedUsers = [{'userName': m.lower(), 'service': activeUsers[m]} for m in re.findall(atMentionRegex, messageText) if m in activeUsers.keys()]
    print(f'MENTION: {mentionedUsers}')
    if mentionedUsers:
        return mentionedUsers
    return None

def checkForCommand(messageText):
    if messageText.startswith('!'):
        return True
    return False

botCommands = None
botCommandHeaders = None
commandTemplate = Template('${command}-${service}')
commandRefreshTime = -10000
def getCommandsFromSheet(overrideRefresh=False):
    services = CONFIG['GENERAL']['services'].split(',')

    global commandRefreshTime, botCommands, botCommandHeaders
    if overrideRefresh or not botCommands or (time.time() - commandRefreshTime) > CONFIG.getint('GENERAL', 'commandRefreshIntervalMin')*60:
        print('Pulling commands from sheet again...')
        commandRefreshTime = time.time()

        commandsWorksheet = sheet.worksheet_by_title(CONFIG['SHEET']['commandsSheetName'])
        botCommandHeaders = commandsWorksheet.get_values(start='A2', end='K2', returnas='matrix')[0]
        commandsData = commandsWorksheet.get_values(start='A3', end='K100', include_tailing_empty=False, returnas='matrix')

        commandsList = []
        for row in commandsData:
            if row[0] != '' and row[0] != 'VideoID':
                commandsList.append({ x.lower(): y for (x,y) in zip(botCommandHeaders, row)})

        botCommands = {}
        for command in [c for c in commandsList if c['enabled'] == 'TRUE']:
            if command['service'] != 'All':
                botCommands[commandTemplate.safe_substitute(command)] = command
            elif command['service'] == 'All':
                for service in services:
                    subCommand = {
                        'command': command['command'],
                        'service': service
                    }
                    botCommands[commandTemplate.safe_substitute(subCommand)] = command
        
        print('Data from sheet pulled successfully...')

extractMatchGroups = r'([$][{][^ }]+[}])'
def getResponse(messageText, service, isMod):
    getCommandsFromSheet(overrideRefresh=('!refresh' == messageText.split(' ')[0] and isMod))
    
    print(botCommands)

    command = commandTemplate.safe_substitute({
        'command': messageText.split(' ')[0],
        'service': service
    })

    if command in botCommands:
        print(f'Processing command: {command}...')
        
        response = botCommands[command]['response']
        
        if 'regex' in botCommands[command]:
            responseTokens = re.findall(extractMatchGroups, botCommands[command]['response'])

            requestTokens = {}
            for groupIter in re.finditer(botCommands[command]['regex'], messageText):
                for key in groupIter.groupdict():
                    requestTokens[f'${{{key}}}'] = groupIter.groupdict()[key]
            
            for addTokens in botCommandHeaders[3:]:
                if addTokens in botCommands[command]:
                    requestTokens[f'${{{addTokens}}}'] = botCommands[command][addTokens]

            for token in responseTokens:
                if token in requestTokens:
                    response = response.replace(token, requestTokens[token])

        return response.split("<br>")
    return None

# TWITCH
class TwitchUpdateClient(twitchio.Client):
    def __init__(self, token, client_secret, initial_channels):
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop.run_until_complete(self.event_token_expired())
        
        super().__init__(token=CONFIG['TWITCH_ACCT']['accessToken'], client_secret=client_secret, initial_channels=initial_channels)

    async def event_token_expired(self):
        botParams = {
            "client_id": CONFIG['TWITCH_ACCT']['clientId'],
            "client_secret": CONFIG['TWITCH_ACCT']['clientSecret'],
            "grant_type": "refresh_token",
            "refresh_token": CONFIG['TWITCH_ACCT']['refreshToken']
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post("https://id.twitch.tv/oauth2/token", params=botParams) as response:
                token = await response.json()
                CONFIG['TWITCH_ACCT']['accessToken'] = token['access_token']     

    async def event_ready(self):
        print('Updating Twitch Title and Game!')

        global youtubeVideoIds
        videoDataService = AuthManager.get_authenticated_service(CONFIG['LIVECHATBOT-READONLY'], 
                                                                 authConfig=CONFIG['AUTH_MANAGER'])
        videoDataRequest = videoDataService.videos().list(
            part="snippet,contentDetails,statistics",
            id=youtubeVideoIds[0])

        videoDataResponse = videoDataRequest.execute()
        livestreamName = videoDataResponse['items'][0]['snippet']['title']
        gameName = re.findall(r'[(]([^)]+)[)]', videoDataResponse['items'][0]['snippet']['title'])
        gameName = gameName[0] if gameName else "Just Chatting"
        await self.change_stream_info(livestreamName, gameName)
        
        print('Twitch: Title and Game Set... closing acct connection.')
        await self.close()
        print('Closed.')

    async def change_stream_info(self, title, game):
        print("Updating stream info...")
        
        games = await self.fetch_games(names=[game])
        if not games:
            print('\tGame not found, defaulting to just chatting...')
            games = await self.fetch_games(names=["Just Chatting"])

        user = self.create_user(self.user_id,
                                CONFIG['TWITCH_ACCT']['twitchChannelName'])
        await user.modify_stream(CONFIG['TWITCH_ACCT']['accessToken'],
                                 game_id=games[0].id,
                                 title=title)
        print("Stream info updated.")

class TwitchClient(twitchio.Client):  
    RESPONSE_CHANNEL = None
    
    def __init__(self, token, client_secret, initial_channels):
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop.run_until_complete(self.event_token_expired())
        
        super().__init__(token=CONFIG['TWITCH_BOT']['accessToken'], client_secret=client_secret, initial_channels=initial_channels)

    async def event_ready(self):
        print('Twitch Ready!')
        self.RESPONSE_CHANNEL = self.get_channel(CONFIG['TWITCH_ACCT']['twitchChannelName'])
    
    async def event_token_expired(self):
        botParams = {
            "client_id": CONFIG['TWITCH_BOT']['clientId'],
            "client_secret": CONFIG['TWITCH_BOT']['clientSecret'],
            "grant_type": "refresh_token",
            "refresh_token": CONFIG['TWITCH_BOT']['refreshToken']
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post("https://id.twitch.tv/oauth2/token", params=botParams) as response:
                token = await response.json()
                CONFIG['TWITCH_BOT']['accessToken'] = token['access_token']           

    async def event_message(self, message):       
        messageText = message.content
        
        if checkForCommand(messageText):
            messagesToSend = getResponse(messageText, 'Twitch', message.author.is_mod)

            print('Sending messages to Twitch...')
            if messagesToSend:
                for messageToSend in messagesToSend:
                    print(messageToSend)
                    if messageToSend:
                        print('Sending message to Twitch...')
                        await self.RESPONSE_CHANNEL.send(messageToSend)
                return

        if not message.author:
            print('Message is from a bot, ignoring...')
            return

        if message.author.name not in twitchProfileCache.keys():
            user = None
            for user in await self.fetch_users(names=[message.author.name]):
                print('Got offline profile picture for '+message.author.name)
                twitchProfileCache[message.author.name] = user
        print(f'EMOTE RAW THING: {message.raw_data}')
        messageWithEmote = twitchEmoteSubs(messageText,
                [e for e in message.raw_data.split(';') if e.startswith('emotes')][0])
        messageWithEmote = bttvSafeSub(messageWithEmote)

        (messageId, messageDict) = twitchMsgToJSON(message, twitchProfileCache[message.author.name], messageWithEmote)
        activeUsers[messageDict['username'].lower()] = 'Twitch'

        if bannedUserIds[messageDict['userId']]:
            print('Banned User: %s [%s] : Ignoring Message' % (messageDict['username'], messageDict['userId']))
        else:
            websocketServer.send_message_to_all(buildMsg('NEW', message=messageDict))
            discordSendMsg(':purple_square: **'+message.author.name+"**", messageId, messageDict['messageText'])

twitchClient = None
twitchClientEventLoop = None
def twitchServerThreadTarget():
    global twitchClientEventLoop
    if not twitchClientEventLoop:
        twitchClientEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(twitchClientEventLoop)

    global twitchClient
    twitchClient = TwitchClient(token=CONFIG['TWITCH_BOT']['accessToken'],
                                client_secret=CONFIG['TWITCH_BOT']['clientSecret'],
                                initial_channels=[CONFIG['TWITCH_ACCT']['twitchChannelName']])
    twitchClient.run()

twitchAcctClient = None
twitchAcctClientEventLoop = None
def twitchAcctServerThreadTarget():
    global twitchAcctClientEventLoop
    if not twitchAcctClientEventLoop:
        twitchAcctClientEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(twitchAcctClientEventLoop)

    global twitchAcctClient
    twitchAcctClient = TwitchUpdateClient(token=CONFIG['TWITCH_ACCT']['accessToken'],
                                          client_secret=CONFIG['TWITCH_ACCT']['clientSecret'],
                                          initial_channels=[CONFIG['TWITCH_ACCT']['twitchChannelName']])
    twitchAcctClient.run()

twitchIdParser = re.compile(r';id=([^;]+)')
def twitchMsgToJSON(message, user, msgHTML):
    id = uuid.uuid4().hex
    messageDict = {   
        'id': id,
        'username': user.display_name,
        'userId': message.author.name,
        'time': str(message.timestamp),
        'messageText': message.content,
        'messageHTML': msgHTML,
        'service': 'twitch',
        'serviceURL': 'img/twitch_badge_1024.png',
        'eventType': 'ChatMessage',
        'avatarURL': user.profile_image,
        'reactions': [],
        'images': []
    }
    messageLog[id] = messageDict
    messageLogOrdered.append(messageDict)
    return (id, messageDict)

def twitchEmoteSubs(messageText, substitutionText):
    edits = []
    messageParts = []

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

        messageToProcess = messageText
        for edit in edits:
            msgAfter = html.escape(messageToProcess[(edit[1]['end']+1):])
            messageToProcess = messageToProcess[:edit[1]['start']]

            print(f'[{messageToProcess}] => [{msgAfter}]')

            emoteEmbed = twitchEmoteTemplate.safe_substitute({
                'id': edit[1]['id'],
                'format': 'default',
                'theme_mode': 'dark',
                'scale': '3.0'})
            
            messageParts.append(msgAfter)
            messageParts.append(emoteEmbed)
        
        messageParts.append(html.escape(messageToProcess))
        messageParts.reverse()

        return ''.join(messageParts)
    else:
        return html.escape(messageText)
    

TWITCH_MAX_MSG_LENGTH = 400
async def twitchSendMessage(messageText):
    if len(messageText) > TWITCH_MAX_MSG_LENGTH:
        print(f'[TWITCH] Message too long, not sending: "{messageText}"')
        return
    
    await twitchClient.RESPONSE_CHANNEL.send(messageText)

# BTTV
bttvEmotes = {}

def splitIgnoreHTML(str, splitChar):
    inGT = False
    splits = []
    prev = 0

    for i, c in enumerate(str):
        if c == "<":
            inGT = True
        elif c == ">":
            inGT = False
        elif c == splitChar and not inGT:
            splits.append(str[prev:i].strip())
            prev = i
    splits.append(str[prev:].strip())
    
    return splits

def getBTTVEmotes():
    base_url = "https://api.betterttv.net/3"
    global_endpoint = "/cached/emotes/global"
    user_endpoint = "/cached/users/twitch/84170686"

    # Send requests
    global_response = requests.get(base_url + global_endpoint)
    user_response = requests.get(base_url + user_endpoint)

    # Check for successful responses
    if global_response.status_code == 200 and user_response.status_code == 200:
        emotes = {}
        
        # Parse JSON responses
        global_data = global_response.json()
        user_data = user_response.json()

        # Print emote names from global emotes
        for emote in global_data:
            emotes[emote['code']] = emote

        # Get shared channel emotes
        for emote in user_data['sharedEmotes']:
            emotes[emote['code']] = emote

        # Get channel specific emotes
        for emote in user_data['channelEmotes']:
            emotes[emote['code']] = emote

        return emotes
    else:
        print("Error:", global_response.status_code, global_response.text)
        print("Error:", user_response.status_code, user_response.text)

def bttvSafeSub(message):
    global bttvEmotes
    msgParts = splitIgnoreHTML(message, " ")
    print(msgParts)
    
    for num, word in enumerate(msgParts):
        if word.strip(':') in bttvEmotes:
            msgParts[num] = bttvEmoteTemplate.safe_substitute(bttvEmotes[word.strip(':')])

    return " ".join(msgParts)

# YOUTUBE
youtubeAPI = None

def youtubeStart():
    global CONFIG, youtubeVideoIds, chatbotService, liveChatId, ytBotChannelId
    bcastService = AuthManager.get_authenticated_service(CONFIG['LIVECHATBOT-RECV'], 
                                                         authConfig=CONFIG['AUTH_MANAGER'])

    chatbotService = AuthManager.get_authenticated_service(CONFIG['LIVECHATBOT-SEND'], 
                                                           authConfig=CONFIG['AUTH_MANAGER'])

    request = bcastService.liveBroadcasts().list(
        part='snippet',
        id=youtubeVideoIds[0]
    )
    response = request.execute()
    liveChatId = response['items'][0]['snippet']['liveChatId']

    request = chatbotService.channels().list(
        part="snippet",
        mine=True
    )
    response = request.execute()
    ytBotChannelId = response['items'][0]['id']

    youtubeAPI = YoutubeLivechat(youtubeVideoIds,
                                 ytBcastService=bcastService,
                                 callbacks=[youtubeCallback])

    if not CONFIG.getboolean('DEV', 'testMode'):
        request = bcastService.liveBroadcasts().update(
            part='status',
            body={
            'id': youtubeVideoIds[0],
            'status': {
                'privacyStatus': 'public'
            }
            }
        )
        response = request.execute()

    youtubeAPI.start()

def youtubeCallback(message):
    contentEscaped = message['htmlText']

    if message['authorDetails']['channelId'] == ytBotChannelId:
        print('Ignoring chatbot message...')
        return

    if checkForCommand(message['snippet']['displayMessage']):
        messagesToSend = getResponse(message['snippet']['displayMessage'], 
                                     'YouTube',
                                     message['authorDetails']['isChatModerator'] or message['authorDetails']['isChatOwner'])
        
        if messagesToSend:
            for messageToSend in messagesToSend:
                if messageToSend:
                        print('Sending message to YouTube...')
                        youtubeSendMessage(messageToSend)
            return
    
    global websocketServer
    messageHTML = youtubeEmoteSubs(contentEscaped)
    print("PRE: "+messageHTML)
    messageHTML = bttvSafeSub(messageHTML)
    print("POST: "+messageHTML)
    (messageId, messageDict) = youtubeMsgToJSON(message, messageHTML)

    activeUsers[messageDict['username'].lower()] = 'YouTube'

    if bannedUserIds[messageDict['userId']]:
        print('Banned User: %s [%s] : Ignoring Message' % (messageDict['username'], messageDict['userId']))
    else:
        websocketServer.send_message_to_all(buildMsg('NEW', message=messageDict))
        discordSendMsg(':red_square: **'+message['authorDetails']['displayName']+'**', messageId, messageDict['messageText'])

YT_MAX_MSG_LENGTH = 200
def youtubeSendMessage(messageText):
    if len(messageText) > YT_MAX_MSG_LENGTH:
        print(f'[YOUTUBE] Message too long, not sending: "{messageText}"')
        return

    request = chatbotService.liveChatMessages().insert(
        part="snippet",
        body={
          "snippet": {
            "liveChatId": liveChatId,
            "type": "textMessageEvent",
            "textMessageDetails": {
              "messageText": messageText
            }
          }
        }
    )

    return request.execute()

def youtubeMsgToJSON(msg, msgHTML):
    id = uuid.uuid4().hex

    messageDict = {
      'id': id,
      'username': msg['authorDetails']['displayName'],
      'userId': msg['authorDetails']['channelId'],
      'time': msg['snippet']['publishedAt'],
      'messageText': msg['snippet']['displayMessage'],
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
            msg += html.escape(item['text'])
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
    global CONFIG, discordThread, currentDiscordThreadId
    print('[DISCORD] We have logged in as {0.user}'.format(discordClient))
    
    if CONFIG.getboolean('DEV', 'testMode'):
        currentDiscordThreadId = int(CONFIG['DEV']['testChannelId'])
        discordChannel = discordClient.get_channel(int(CONFIG['DEV']['testChannelId'])) #Test Channel
        discordThread = discordClient.get_channel(int(CONFIG['DEV']['testChannelId'])) #Test Channel
        
        print(f'Running client in TEST mode discord thread {currentDiscordThreadId}...')
        print(f'Discord Channel: {discordChannel}')
        print(f'Discord Thread: {discordThread}')
    else:
        discordChannel = discordClient.get_channel(int(CONFIG['CLIENT']['discordChannelId']))

        global youtubeVideoIds
        videoDataService = AuthManager.get_authenticated_service(CONFIG['LIVECHATBOT-READONLY'], 
                                                                 authConfig=CONFIG['AUTH_MANAGER'])
        videoDataRequest = videoDataService.videos().list(
            part="snippet,contentDetails,statistics",
            id=youtubeVideoIds[0])

        videoDataResponse = videoDataRequest.execute()
        livestreamName = videoDataResponse['items'][0]['snippet']['title'] + ' ['+videoDataResponse['items'][0]['snippet']['publishedAt'][0:10]+']'
        
        #Check for existing thread...
        lastThread = discordChannel.threads[-1]

        print(lastThread)
        if lastThread and lastThread.name == livestreamName:
            #Connect to existing thread
            print('Connecting to existing thread...')
            currentDiscordThread = lastThread.id
            discordThread = discordClient.get_channel(lastThread.id)
        else:
            with requests.get(videoDataResponse['items'][0]['snippet']['thumbnails']['standard']['url']) as r:
                img = Image.open(BytesIO(r.content), mode='r', formats=['JPEG'])
                tmpImg = img.crop((0,60,640,420))
                croppedBytes = BytesIO()
                tmpImg.save(croppedBytes, format='PNG')
                croppedBytes.seek(0)

                picture = discord.File(croppedBytes, filename='thumbnail.png', description='YouTube Thumbnail Picture')
                links = 'Going Live Shortly!\n>>> <https://youtu.be/'+youtubeVideoIds[0]+'>\n<http://twitch.tv/'+CONFIG['GENERAL']['twitchChannelName']+'>'
                message = await discordChannel.send(content=links, file=picture)

            if currentDiscordThreadId is None:
                print('Creating new discord thread...')
                discordThread = await discordChannel.create_thread(name=livestreamName,
                                                                    message=message,
                                                                    auto_archive_duration=1440)
                currentDiscordThread = discordThread.id
            else:
                print('Connection reset, reusing existing discordThread [%s].' % currentDiscordThreadId)
                discordThread = discordClient.get_channel(currentDiscordThreadId)

        print('1 Thread: '+str(discordThread))

messageQueue = {}

outwardDiscordMsgTemplate = Template('[discord] ${senderName}: ${msgText}')
@discordClient.event
async def on_message(message):
    global discordThread, messageQueue
    
    msgText = html.escape(message.clean_content)

    if hasattr(message.author, 'roles'):
        isMod = any([role.name for role in message.author.roles if role.name in CONFIG['DISCORD']['modRoles'].split(',')])
    else:
        isMod = False

    if message.type == discord.MessageType.reply and message.channel.id == discordThread.id:
        messagesToSend = None
        targetMessage = discordClient.get_message(message.reference.message_id)

        if checkForCommand(msgText):
            if ':purple_square:' in targetMessage.clean_content:
                messagesToSend = getResponse(msgText, 'Twitch', isMod)
            elif ':red_square:' in targetMessage.clean_content:
                messagesToSend = getResponse(msgText, 'YouTube', isMod)
            else:
                messagesToSend = getResponse(msgText, 'Discord', isMod)
        else:
            messagesToSend = [ outwardDiscordMsgTemplate.safe_substitute({
                'senderName': message.author.name,
                'msgText': msgText
            }) ]
        
        if ':purple_square:' in targetMessage.clean_content:
            print(f'Forward message to Twitch: {messagesToSend}')
            if messagesToSend:
                for messageToSend in messagesToSend:
                    await twitchSendMessage(messageToSend)
        elif ':red_square:' in targetMessage.clean_content:
            print(f'Forward message to YouTube: {messagesToSend}')
            if messagesToSend:
                for messageToSend in messagesToSend:
                    youtubeSendMessage(messageToSend)
    elif not message.author.bot and checkAtMention(msgText) and message.channel.id == discordThread.id:
        messagesToSend = [ outwardDiscordMsgTemplate.safe_substitute({
            'senderName': message.author.name,
            'msgText': msgText
        }) ]

        print(f'{checkAtMention(msgText)[0]["userName"]} @mentioned a user in discord...')
        if checkAtMention(msgText)[0]['service'] == 'YouTube':
            print(f'Forward message to YouTube: {messagesToSend}')
            if messagesToSend:
                for messageToSend in messagesToSend:
                    youtubeSendMessage(messageToSend)
        elif checkAtMention(msgText)[0]['service'] == 'Twitch':
            print(f'Forward message to Twitch: {messagesToSend}')
            if messagesToSend:
                for messageToSend in messagesToSend:
                    await twitchSendMessage(messageToSend)
    elif checkForCommand(msgText):
        messagesToSend = getResponse(msgText, 'Discord', isMod)
        print('Sending message to Discord...')
        if messagesToSend:
            for messageToSend in messagesToSend:
                await waitAndSendDiscordMessage(messageToSend, uuid.uuid4().hex)
        return

    if not message.author.bot and message.channel.id == discordThread.id:
        print('[DISCORD] Message: '+str(message))
        
        # Await embed changes...
        messageQueue[message.id] = message
        await asyncio.sleep(.5)
        message = messageQueue[message.id]
        del messageQueue[message.id]

        messageHTML = discordEmoteSubs(msgText)
        
        images = [image.url for image in message.attachments + message.stickers]
        embeds = []
        
        print(f'EMBEDS: {message.embeds}')
        for embed in message.embeds:
            print(f'Embed is of type "{embed.type}":')
            if embed.type == 'gifv':
                print(f'EMBED IMAGE PROXY URL: {embed.image.proxy_url}')
                print(f'EMBED VIDEO PROXY URL: {embed.video.proxy_url}')
                images.append(embed.video.proxy_url)
                embeds.append(embed.url)
            elif embed.type == 'rich':
                print('EMBED ERROR: No support for rich yet...')
            elif embed.type ==  'image':
                print('EMBED ERROR: No support for image yet...')
            elif embed.type == 'video':
                print('EMBED ERROR: No support for video yet...')
            elif embed.type == 'article':
                print('EMBED ERROR: No support for article yet...')
            elif embed.type == 'link':
                print('EMBED ERROR: No support for link yet...')
            else:
                print('Embed type unrecognized skipping embed...')

        (id, messageDict) = discordMsgToJSON(message, messageHTML, images)
        discordToWebIdMap[message.id] = id

        # strip embeds from message
        for embed in embeds:
            messageDict['messageText'] = messageDict['messageText'].replace(embed, '')
            messageDict['messageHTML'] = messageDict['messageHTML'].replace(embed, '')

        if bannedUserIds[messageDict['userId']]:
            print('Banned User: %s [%s] : Ignoring Message' % (messageDict['username'], messageDict['userId']))
        else:
            websocketServer.send_message_to_all(buildMsg('NEW', message=messageDict))

@discordClient.event
async def on_message_edit(before, after):
    global messageQueue
    print('EMBED UPDATE')
    if before.id in messageQueue:
        messageQueue[before.id] = after

@discordClient.event
async def on_raw_reaction_add(reaction):
    global discordThread
    if reaction.channel_id == discordThread.id:
        print('[DISCORD] Reaction: '+str(reaction))
        
        messageId = reaction.message_id
        if messageId in discordToWebIdMap.keys():
            messageId = discordToWebIdMap[messageId]

        if len(messageLog[messageId]['images']) == 0:
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

# KICK
def kickCallback(message):
    print('NOTIFY: %s' % message['html_text'])
    print(message)

    if checkForCommand(message['msg_content']):
        # messageToSend = getResponse(message['msg_content'], 
        #                             'Kick',
        #                             message['authorDetails']['isChatModerator'] or message['authorDetails']['isChatOwner'])
        # if messageToSend:
        print('Sending messages to Kick currently unsupported...')
                # youtubeSendMessage(messageToSend)
        return
    
    global websocketServer
    messageHTML = message['html_text']
    (messageId, messageDict) = kickMsgToJSON(message, messageHTML)

    activeUsers[messageDict['username'].lower()] = 'Kick'

    if bannedUserIds[messageDict['userId']]:
        print('Banned User: %s [%s] : Ignoring Message' % (messageDict['username'], messageDict['userId']))
    else:
        websocketServer.send_message_to_all(buildMsg('NEW', message=messageDict))
        discordSendMsg(':green_square: **'+messageDict['username']+'**', messageId, messageDict['messageText'])

def kickMsgToJSON(msg, msgHTML):
    messageDict = {
      'id': msg['msg_id'],
      'username': msg['username'],
      'userId': msg['user_id'],
      'time': msg['timestamp'],
      'messageText': msg['msg_content'],
      'messageHTML': msgHTML,
      'service': 'kick',
      'serviceURL': 'img/kick_badge_1024.png',
      'avatarURL': msg['user_avatar'],
      'reactions': [],
      'images': []
    }
    messageLog[msg['msg_id']] = messageDict
    messageLogOrdered.append(messageDict)
    return (msg['msg_id'], messageDict)    

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
    global CONFIG, bttvEmotes
    print("Getting BTTV Emote List...")
    bttvEmotes = getBTTVEmotes()
    
    print("HTTP Server Thread Starting...")
    httpServerThread = threading.Thread(target=httpServerThreadTarget,
                                        daemon=True)
    httpServerThread.start()

    print("Connecting to Twitch...")
    twitchClientThread = threading.Thread(target=twitchServerThreadTarget,
                                          daemon=True)
    twitchClientThread.start()

    twitchAcctClientThread = threading.Thread(target=twitchAcctServerThreadTarget,
                                              daemon=True)
    twitchAcctClientThread.start()

    print("Connecting to Kick...")
    kickMonitor = KickLivechat('aldenpotamus')
    kickMonitor.registerNewCallback(kickCallback)

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
    print(f'Running for videos: {sys.argv[1]}')
    youtubeVideoIds = str(sys.argv[1]).split(',')
    print(youtubeVideoIds)
    del sys.argv[1]

    print('Parsing config file...')
    CONFIG = configparser.ConfigParser()
    CONFIG.read('config.ini')

    print('Getting google sheet with commands data...')
    gc = pygsheets.authorize(service_file=CONFIG['SHEET']['serviceToken'])
    sheet = gc.open_by_key(CONFIG['SHEET']['id'])

    print('Running chatDaemon...')
    print('Args: '+str(sys.argv))

    main()
