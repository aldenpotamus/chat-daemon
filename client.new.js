var ws;

var SERVICES = {
    'discord': './img/discord_badge_1024.png',
    'youtube': './img/youtube_badge_1024.png',
    'twitch': './img/twitch_badge_1024.png'
}

function init() {
    if(window.location.search == '?admin'){
        console.log('Running as admin...');
        document.body.classList.add('admin');
    } else {
        document.body.classList.add('non-admin');
    }

    if (window.location.hostname != '') {
        var wsAddress = 'ws://' + window.location.hostname + ':9001/';
        console.log(wsAddress);
        ws = new WebSocket(wsAddress)
    } else {
        ws = new WebSocket('ws://localhost:9001/');
    }

    ws.onopen = function () { console.log('onOPEN'); };
    ws.onclose = function () { console.log("onCLOSE"); };
   
    ws.onmessage = function (e) {
        output(e.data);
    };
    ws.onerror = function (e) {
        console.log('onERROR');
        console.log(e)
    };

    testMessage();
    //handleMessage(JSON.parse('{"action": "HIDE", "id": "1"}'));
    //handleMessage(JSON.parse('{"action": "UNHIDE", "id": "1"}'));
    handleMessage(JSON.parse('{"action": "UNBAN", "ids": [1, 12]}'));
}

function handleMessage(messageJSON) {
    console.log("HandleMessage: "+messageJSON);

    switch(messageJSON['action']) {
        case 'DUMMY':
        case 'MSG':
            // buildMessage
        break;
        case 'REACTION':

        break;
        case 'PIN':
            console.log('Pinning message'+messageJSON)
            pinMessage(document.getElementById(messageJSON['id']));
        break;
        case 'UNPIN':
            console.log('Unpinning message'+messageJSON)
            unpinMessage(document.getElementById(messageJSON['id']));
        break;
        case 'HIDE':
            console.log('Hiding message'+messageJSON)
            hideMessage(document.getElementById(messageJSON['id']));
        break;
        case 'UNHIDE':
            console.log('Unhiding message'+messageJSON)
            unhideMessage(document.getElementById(messageJSON['id']));
        break;
        case 'BAN':
            console.log('Banning message'+messageJSON)
            messageJSON['ids'].forEach(id => {
                banMessage(document.getElementById(id));
            });
        break;
        case 'UNBAN':
            console.log('Unbanning message'+messageJSON)
            messageJSON['ids'].forEach(id => {
                unbanMessage(document.getElementById(id));
            });
        break;
        case 'RELOAD':
            // reloadMessages(param);
        break;
        case 'CLEAR':
            document.getElementById('messages').innerHTML = ''
        break;       
    }
  }

function testMessage() {
    shortMsg = "This is a test message...";
    longMsg = "Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged. It was popularised in the 1960s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop publishing software like Aldus PageMaker including versions of Lorem Ipsum.";

    buildMessage("1", shortMsg, 'Ralph', 'twitch', './img/blank_profile_pic.png', null, "");
    buildMessage("12", longMsg, 'Bob', 'discord', './img/blank_profile_pic.png', null, "");
    buildMessage("123", shortMsg, 'Aldenpotamus', 'youtube', './img/blank_profile_pic.png', null, "");
    buildMessage("1234", shortMsg, 'Fredrick the Great', 'twitch', './img/blank_profile_pic.png', "./img/twitch_generic_1024.png", "");
    buildMessage("12345", longMsg, 'RB', 'discord', './img/blank_profile_pic.png', "./img/twitch_generic_1024.png", "");
}

function unhideMessage(messageDiv) {
    messageDiv.classList.remove('hidden');
}

function hideMessage(messageDiv) {
    messageDiv.classList.add('hidden');
}

function toggleMessageVisibility(messageDiv) {
    messageDiv.classList.contains('hidden') ? unhideMessage(messageDiv) : hideMessage(messageDiv);
}

function pinMessage(messageDiv) {
    messageDiv.classList.add('pinned');
}

function unpinMessage(messageDiv) {
    messageDiv.classList.remove('pinned');
}

function toggleMessagePinStatus(messageDiv) {
    messageDiv.classList.contains('pinned') ? unpinMessage(messageDiv) : pinMessage(messageDiv);   
}

function banMessage(messageDiv) {
    messageDiv.classList.add('banned');
}

function unbanMessage(messageDiv) {
    messageDiv.classList.remove('banned');
}

function toggleMessageBanStatus(messageDiv) {
    messageDiv.classList.contains('banned') ? unbanMessage(messageDiv) : banMessage(messageDiv);
}

function dismissMessage(messageDiv) {
    messageDiv.classList.add('dismissed');
}

function buildMessage(msgId, messageText, userName, service, profilePicURL, imageURL, reactions) {
    var template = document.getElementById('messageTemplate');
    var instance = template.content.cloneNode(true)

    instance.querySelector('.message').id = msgId;
    
    instance.querySelector('.message').classList.add(service);
    if(messageText.length > 50) instance.querySelector('.message').classList.add('long');

    if(imageURL) {
        instance.querySelector('.message').classList.add('img');
        
        var image = document.createElement('img');
        image.src = imageURL;
        image.referrerpolicy = 'no-referrer'

        instance.querySelector('.message').insertBefore(image, instance.querySelector('.message > .content'));
    } else {
        instance.querySelector('.message').classList.add('text');
    }

    instance.querySelector('#user-pic > img').src = profilePicURL;
    instance.querySelector('#user-service > img').src = SERVICES[service];
    instance.querySelector('#user-name').innerHTML = userName.toUpperCase();
    instance.querySelector('#reactions').innerHTML = reactions;
    
    instance.querySelector('.content').innerHTML = messageText;

    document.getElementById('messages').appendChild(instance);
}