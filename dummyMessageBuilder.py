import json
from string import Template

messageTemplate = Template('''{
    "id": "${id}",
    "userName": "${userName}",
    "time": "${time}",
    "messageText": "${messageText}",
    "messageHTML": "${messageHTML}",
    "service": "${service}",
    "serviceURL": "${serviceURL}",
    "eventType": "${eventType}",
    "avatarURL": "${avatarURL}"
}''')

dummyMessages = {
    'YT:ShortTextMessage': messageTemplate.safe_substitute({
        'id': 'null',
        'userName': 'username',
        'time': '1650226633808',
        'messageText': 'short youtube message',
        'messageHTML': 'short youtube message',
        'service': 'YouTube',
        'serviceURL': 'img/youtube_badge_1024.png',
        'eventType': 'ChatMessage',
        'avatarURL': 'https://yt4.ggpht.com/ytc/AKedOLRhLTJY1OfImo7K1VzRLAo3C7T4s9FcrqSwTR7X=s64-c-k-c0x00ffffff-no-rj'
    }),
    'YT:LongTextMessage': messageTemplate.safe_substitute({
        'id': 'null',
        'userName': 'username',
        'time': '1650226633808',
        'messageText': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.',
        'messageHTML': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.',
        'service': 'YouTube',
        'serviceURL': 'img/youtube_badge_1024.png',
        'eventType': 'ChatMessage',
        'avatarURL': 'https://yt4.ggpht.com/ytc/AKedOLRhLTJY1OfImo7K1VzRLAo3C7T4s9FcrqSwTR7X=s64-c-k-c0x00ffffff-no-rj'
    }),
    'TW:ShortTextMessage': messageTemplate.safe_substitute({
        'id': 'null',
        'userName': 'username',
        'time': '1650226558.5448346',
        'messageText': 'short twitch message',
        'messageHTML': 'short twitch message',
        'service': 'Twitch',
        'serviceURL': 'img/twitch_badge_1024.png',
        'eventType': 'ChatMessage',
        'avatarURL': 'https://static-cdn.jtvnw.net/jtv_user_pictures/a7185a11-3dbb-4ba2-8dca-17c9f569f293-profile_image-300x300.png'
    }),
    'TW:LongTextMessage': messageTemplate.safe_substitute({
        'id': 'null',
        'userName': 'username',
        'time': '1650226558.5448346',
        'messageText': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.',
        'messageHTML': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.',
        'service': 'Twitch',
        'serviceURL': 'img/twitch_badge_1024.png',
        'eventType': 'ChatMessage',
        'avatarURL': 'https://static-cdn.jtvnw.net/jtv_user_pictures/a7185a11-3dbb-4ba2-8dca-17c9f569f293-profile_image-300x300.png'
    }),
    'DC:ShortTextMessage': messageTemplate.safe_substitute({
        "id": "null",
        "userName": "username",
        "time": "966188396810743848",
        "messageText": "short discord message",
        "messageHTML": "short discord message",
        "service": "Discord",
        "serviceURL": "img/discord_badge_1024.png",
        "eventType": "MessageType.default",
        "avatarURL": "https://cdn.discordapp.com/avatars/430497076271644673/9317516e976c6a8c5789d746c0600d64.webp?size=1024"
    }),
    'DC:LongTextMessage': messageTemplate.safe_substitute({
        "id": "null",
        "userName": "username",
        "time": "966188396810743848",
        'messageText': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.',
        'messageHTML': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.',
        "service": "Discord",
        "serviceURL": "img/discord_badge_1024.png",
        "eventType": "MessageType.default",
        "avatarURL": "https://cdn.discordapp.com/avatars/430497076271644673/9317516e976c6a8c5789d746c0600d64.webp?size=1024"
    })
}

with open('dummy_messages.json', 'w') as file:
    json.dump(dummyMessages, file)