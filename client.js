var ws;

var SERVICES = {
    'discord': './img/discord_badge_1024.png',
    'youtube': './img/youtube_badge_1024.png',
    'twitch': './img/twitch_badge_1024.png'
}

var maxMessages = 6;
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
        handleMessage(JSON.parse(e.data));
    };
    ws.onerror = function (e) {
        console.log('onERROR');
        console.log(e)
    };
}

function handleMessage(messageJSON) {
    console.log('Messge from Server:');
    console.log(messageJSON)

    switch(messageJSON['action']) {
        case 'NEW':
            console.log('Display New Message');
            if(document.getElementById(messageJSON.payload.message.id)) return;

            console.log('\tCreating new message...');
            message = messageJSON.payload.message

            if((document.body.classList.contains('non-admin') && !message.images.length) ||
                document.body.classList.contains('admin') ) {
                    constructMessage(message.id,
                                     message.messageText,
                                     message.messageHTML,
                                     message.username,
                                     message.service,
                                     message.avatarURL,
                                     message.images ? message.images[0] : null,
                                     message.reactions);
                } else {
                    console.log('\tSkipping NEW for non-admin IMG message.')
                }
            break;
        case 'SHOW':
            console.log('Showing Message')
            
            if(!document.getElementById(messageJSON.payload.message.id)) {
                console.log('\tMessage not present, loading from payload...');
                if(messageJSON.payload.message) {
                    message = messageJSON.payload.message;
                    constructMessage(message.id,
                                     message.messageText,
                                     message.messageHTML,
                                     message.username,
                                     message.service,
                                     message.avatarURL,
                                     message.images ? message.images[0] : null,
                                     message.reactions);
                } else {
                    console.log('\t[NO-OP] Message not provided from server.')
                }
            } else if (document.body.classList.contains('non-admin')) {
                console.log('\tShowing message already present in DOM...');
                selfDestruct(document.getElementById('messages'), document.getElementById(messageJSON.payload.id));
            }
            
            document.getElementById(messageJSON.payload.id).classList.remove('hidden');
            break;
        case 'HIDE':
            console.log('Hiding Message')
            
            if(!document.getElementById(messageJSON.payload.message.id)) {
                console.log('\t[NO-OP] Message not present in DOM.');
            } else {
                if(document.body.classList.contains('admin')) {
                    console.log('\tADMIN: Skipping Remove Animations');
                    document.getElementById(messageJSON.payload.id).classList.add('hidden');
                } else {
                    document.getElementById(messageJSON.payload.id).classList.add('shiftleft');
                    document.getElementById(messageJSON.payload.id).addEventListener("animationend", function(event) {
                        event.currentTarget.classList.add('hidden');
                        event.currentTarget.classList.remove('shiftleft');

                        if(document.getElementById('messages').contains(event.currentTarget)) {
                            document.getElementById('messages').removeChild(event.currentTarget);
                        }
                    });
                }
            }

            break;
        case 'PIN':
            console.log('Pinning Message')

            if(!document.getElementById(messageJSON.payload.message.id)) {
                console.log('\tMessage not present, loading from payload...');
                if(messageJSON.payload.message) {
                    message = messageJSON.payload.message;
                    constructMessage(message.id,
                                     message.messageText,
                                     message.messageHTML,
                                     message.username,
                                     message.service,
                                     message.avatarURL,
                                     message.images ? message.images[0] : null,
                                     message.reactions);
                } else {
                    console.log('\t[NO-OP] Message not provided from server.')
                }
            }
            
            document.getElementById(messageJSON.payload.id).classList.remove('hidden');
            document.getElementById(messageJSON.payload.id).classList.add('pinned');

            break;
        case 'UNPIN':
            console.log('Un-Pinning Message')
                
            if(!document.getElementById(messageJSON.payload.message.id)) {
                console.log('\t[NO-OP] Message not present in DOM.');
            } else {
                document.getElementById(messageJSON.payload.id).classList.remove('pinned');
            }

            break;
        case 'BAN':
            console.log('Banning Message')
            
            if(!document.getElementById(messageJSON.payload.id)) {
                console.log('\t[NO-OP] Message not present, nothign to ban.')
            } else {
                document.getElementById(messageJSON.payload.id).classList.add('banned');
            }

            break;
        case 'UNBAN':
            console.log('Un-Banning Message')
                
            if(!document.getElementById(messageJSON.payload.id)) {
                console.log('\t[NO-OP] Message not present in DOM.');
            } else {
                document.getElementById(messageJSON.payload.id).classList.remove('banned');
            }

            break;
        case 'REACT':
            console.log('Reaction to Message')
                
            document.getElementById(messageJSON.payload.id).querySelector('#reactions').innerHTML += messageJSON.payload.reactionHMTL;

            break;
        case 'CLEAR':
            document.getElementById('messages').innerHTML = '';
            break;
        case 'RELOAD':
            console.log('Reloading Messages from Server');

            document.getElementById('messages').innerHTML = '';
            messageJSON.payload.messages.forEach(message => {
                constructMessage(message.id,
                                 message.messageText,
                                 message.messageHTML,
                                 message.username,
                                 message.service,
                                 message.avatarURL,
                                 message.images ? message.images[0] : null,
                                 message.reactions);               
            });
            break;
    }
}

function testMessages() {
    shortMsg = "This is a test message...";
    longMsg = "Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged. It was popularised in the 1960s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop publishing software like Aldus PageMaker including versions of Lorem Ipsum.";

    constructMessage("1", shortMsg, shortMsg, 'Ralph', 'twitch', './img/blank_profile_pic.png', null, "");
    constructMessage("12", longMsg, longMsg, 'Bob', 'discord', './img/blank_profile_pic.png', null, "");
    constructMessage("123", shortMsg, shortMsg, 'Aldenpotamus', 'youtube', './img/blank_profile_pic.png', null, "");
    constructMessage("1234", shortMsg, shortMsg, 'Fredrick the Great', 'twitch', './img/blank_profile_pic.png', "./img/twitch_generic_1024.png", "");
    constructMessage("12345", longMsg, longMsg, 'RB', 'discord', './img/blank_profile_pic.png', "./img/twitch_generic_1024.png", "");
}

function buildMsg(action, id, message, username, args) {
    return JSON.stringify({
        'action': action,
        'payload': {
            'id': message ? message['id'] : id,
            'username': message ? message['username'] : username,
            'message': message,
            'args': args
        }
    });
}

function toggleMessageVisibility(messageDiv) {
    messageDiv.classList.contains('hidden') ? action = 'SHOW' : action = 'HIDE';
    ws.send(buildMsg(action, messageDiv.id, null, null, null));
}

function toggleMessagePinStatus(messageDiv) {
    messageDiv.classList.contains('pinned') ? action = 'UNPIN' : action = 'PIN';
    ws.send(buildMsg(action, messageDiv.id, null, null, null));
}

function toggleMessageBanStatus(messageDiv) {
    messageDiv.classList.contains('banned') ? action = 'UNBAN' : action = 'BAN';
    ws.send(buildMsg(action, messageDiv.id, null, null, null));
}

function dismissMessage(messageDiv) {
    messageDiv.classList.add('dismissed');
}

function constructMessage(msgId, messageText, messageHTML, username, service, profilePicURL, imageURL, reactions) {
    var template = document.getElementById('messageTemplate');
    var instance = template.content.cloneNode(true)

    instance.querySelector('.message').id = msgId;
    
    instance.querySelector('.message').classList.add(service);
    if(messageText.length >= 50 || imageURL) instance.querySelector('.message').classList.add('long');

    if(imageURL) {
        instance.querySelector('.message').classList.add('hidden');
        instance.querySelector('.message').classList.add('img');
        
        if(imageURL.includes('.mp4') || imageURL.includes('.ogg') || imageURL.includes('.webm')) {
            var element =  document.createElement('video');
            element.loop = true;
            element.autoplay = "autoplay";
            element.muted = true;
        } else {
            var element = new Image();
        }
        element.src = imageURL;
        element.referrerpolicy = 'no-referrer';
        element.classList.add('discordImg');
        
        instance.querySelector('.message').insertBefore(element, instance.querySelector('.message > .content'));
    } else {
        instance.querySelector('.message').classList.add('text');
    }

    instance.querySelector('#user-pic > img').src = profilePicURL;
    instance.querySelector('#user-service > img').src = SERVICES[service];
    instance.querySelector('#user-name').innerHTML = username;
    instance.querySelector('#reactions').innerHTML = Array.from(reactions).join('');
    
    instance.querySelector('.content').innerHTML = messageHTML;

    document.getElementById('messages').appendChild(instance);
    
    if(document.body.classList.contains('non-admin')) { 
        var newMsg = document.getElementById(msgId);
        newMsg.style.position = 'absolute';
        newMsg.style.transform = 'translateX(-3000%)';

        if(newMsg.querySelector('.discordImg')) {
            // For normal Images
            newMsg.querySelector('.discordImg').addEventListener('load', function(event) {
                animate(newMsg);
                selfDestruct(document.getElementById('messages'), newMsg); 
            });
            // For HTML Video
            newMsg.querySelector('.discordImg').addEventListener('loadeddata', function(event) {
                animate(newMsg);
                selfDestruct(document.getElementById('messages'), newMsg); 
            });
        } else {
            animate(newMsg);
            selfDestruct(document.getElementById('messages'), newMsg); 
        }
    } else {
        console.log('ADMIN: Skipping Add Animations');
    }
}

var bufferOffset = 10;
function animate(msgDiv) {
    var offsetHeight = msgDiv.clientHeight;
    
    console.log('Height of image element: ' + offsetHeight + 'px');
    document.documentElement.style.setProperty('--vOffset', offsetHeight+'px');

    msgDiv.style.position = null;
    msgDiv.style.transform = null;

    Array.from(document.getElementsByClassName('message')).forEach((el) => {
        el.classList.add('shiftup');
        el.addEventListener("animationend", function() {
            el.style.transform = "translate(" + (0) + "px," + (0) + "px)";
            el.classList.remove('shiftup');
            el.style.transform = null;
        });
    });
}

// IN SECONDS
var MESSAGE_TIMEOUT = 30;
function selfDestruct(messages, message) {
    console.log('Starting selfDestruct....')
    return new Promise(resolve => {
        setTimeout(() => {
            if(message.classList.contains('pinned')) {
                resolve('resolved');
                console.log('Message Pinned Sleeping...')
                setTimeout(() => { selfDestruct(messages, message);}, MESSAGE_TIMEOUT*1000);
            } else if (!message.classList.contains('hidden') && messages.contains(message)) {
                ws.send(buildMsg('HIDE', message.id, null, null, null));
            }
        }, MESSAGE_TIMEOUT*1000);
    });
}

function addAnimation(style) {
    if (!dynamicStyles) {
        dynamicStyles = document.createElement('style');
        dynamicStyles.type = 'text/css';
        document.head.appendChild(dynamicStyles);
    }

    dynamicStyles.sheet.insertRule(target, dynamicStyles.length);
}

function clearMessages() {
    ws.send(buildMsg('CLEAR', null, null, null, null));
}

function reloadClients(numMessages) {
    ws.send(buildMsg('RELOAD', null, null, null, numMessages ? [numMessages] : null));
}