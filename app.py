'''
TarungBot
Fasilkom UI 2017 bot
'''

import json
import os
import random
import sys

import dropbox
import requests

from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, ImageSendMessage, TextMessage, TextSendMessage,
    SourceGroup, SourceRoom
)

app = Flask(__name__)

# Get channel_secret and channel_access_token from environment variable
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

TarungBot = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

dropbox_access_token = os.getenv('DROPBOX_ACCESS_TOKEN', None)
dbx = dropbox.Dropbox(dropbox_access_token)

game_data_path = os.getenv('GAME_DATA_PATH', None)
my_id = os.getenv('MY_USER_ID', None)
tickets_path = os.getenv('TICKETS_FILE_PATH', None)

about_msg = ("TarungBot\n"
             "Get to know your Tarung family!\n"
             "---\n"
             "Created by laymonage\n"
             "See the source code at https://github.com/laymonage/TarungBot\n"
             "\n"
             "Also check out @mjb5063s for a multi-purpose bot!")

help_msg = ("/about: send the about message\n"
            "/help: send this help message\n"
            "/bye: make me leave this chat room\n"
            "/start: start the game\n"
            "/restart: restart the game\n"
            "/answer <name>: answer the person in the picture with <name>\n"
            "/a <name>: short for /answer\n"
            "/pass : skip the current person (also /answer pass)\n"
            "/status: show your current game's status\n"
            "/msg <message>: send <message> to the developer")

players = {}

guys = [guy.name.replace('.jpg', '')
        for guy in dbx.files_list_folder(game_data_path + '/male').entries]

gals = [gal.name.replace('.jpg', '')
        for gal in dbx.files_list_folder(game_data_path + '/female').entries]


class Player:
    '''
    A player
    '''
    def __init__(self, user_id):
        self.user_id = user_id
        self.pick = ''
        self.progress = {person: False for person in guys + gals}
        self.correct = 0
        self.wrong = 0
        self.skipped = 0

    def finished(self):
        '''
        Check if a player has finished their game.
        '''
        if self.progress:
            return False
        return True

    def next_link(self):
        '''
        Get next random link.
        '''
        self.pick = random.choice(list(self.progress))
        if self.pick in guys:
            gender = 'male'
        else:
            gender = 'female'
        headers = {
            'Authorization': 'Bearer {}'.format(dropbox_access_token),
            'Content-Type': 'application/json',
        }
        data = '"path": "{}/{}/{}.jpg"'.format(game_data_path,
                                               gender, self.pick)
        data = '{' + data + '}'
        url = 'https://api.dropboxapi.com/2/files/get_temporary_link'
        link = requests.post(url, headers=headers,
                             data=data).json()['link']
        return link

    def answer(self, name):
        '''
        Answer current pick.
        '''
        if self.pick in guys:
            pronoun = ('He', 'him')
        else:
            pronoun = ('She', 'her')
        specific = True

        if name.lower() == 'pass':
            msg = ("{} is {}. Remember {} next time!"
                   .format(pronoun[0], self.pick, pronoun[1]))
            self.skipped += 1

        else:
            for word in name.title().split():
                if word in 'Muhammad' or word in 'Muhamad' or len(word) < 3:
                    specific = False
                    msg = ("Please be more specific. Try again!")
                elif word in self.pick and len(word) >= 3:
                    specific = True
                    msg = ("You are correct! {} is {}."
                           .format(pronoun[0], self.pick))
                    self.correct += 1
                    break
            else:
                if specific:
                    msg = ("You are wrong! {} is {}. Remember {} next time!"
                           .format(pronoun[0], self.pick, pronoun[1]))
                    self.wrong += 1
        if specific:
            del self.progress[self.pick]
        return msg

    def status(self):
        '''
        Return current game's status.
        '''
        return ("{}/{} persons.\n"
                "Correct: {} ({:.2f}%)\n"
                "Wrong: {} ({:.2f}%)\n"
                "Skipped: {} ({:.2f}%)"
                .format(len(guys+gals) - len(self.progress), len(guys+gals),
                        self.correct, self.correct/len(guys+gals)*100,
                        self.wrong, self.wrong/len(guys+gals)*100,
                        self.skipped, self.skipped/len(guys+gals)*100))


@app.route("/callback", methods=['POST'])
def callback():
    '''
    Webhook callback function
    '''
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    '''
    Text message handler
    '''
    text = event.message.text
    if isinstance(event.source, SourceGroup):
        player_id = event.source.group_id
    elif isinstance(event.source, SourceRoom):
        player_id = event.source.room_id
    else:
        player_id = event.source.user_id

    def quickreply(msg):
        '''
        Reply a message with msg as reply content.
        '''
        TarungBot.reply_message(
            event.reply_token,
            TextSendMessage(text=msg)
        )

    def check(user_id):
        '''
        Check if a user is eligible for a game.
        '''
        if user_id not in players:
            msg = "You've never played the game before."
        elif players[user_id].finished():
            msg = ("You have finished the game.\n"
                   "Use /start to start a new one.")
        else:
            return True
        quickreply(msg)
        return False

    def set_player(user_id):
        '''
        Set a new player or reset an existing player.
        '''
        players[user_id] = Player(user_id)

    def can_start_game(user_id):
        '''
        Check if a user can start the game.
        '''
        if user_id in players:
            if not players[user_id].finished():
                return False
        return True

    def send_question(user_id, prev=None):
        '''
        Send a question
        '''
        if not prev:
            content = [TextSendMessage(text="Starting game...")]
        else:
            content = [TextSendMessage(text=prev)]
        link = players[user_id].next_link()
        TarungBot.reply_message(
            event.reply_token, content + [
                ImageSendMessage(
                    original_content_url=link,
                    preview_image_url=link
                ),
                TextSendMessage(text="Who is this person?")
            ]
        )

    def start(user_id, force=False):
        '''
        Start a new game for the user.
        '''
        if not can_start_game(user_id) and not force:
            quickreply(("Your game is still in progress.\n"
                        "Use /restart to restart your progress."))
        else:
            set_player(user_id)
            send_question(user_id)

    def answer(user_id, name):
        '''
        Answer a question.
        '''
        if check(user_id):
            result = players[user_id].answer(name)
            if not players[user_id].finished():
                if 'Try again' in result:
                    quickreply(result)
                else:
                    send_question(user_id, prev=result)
            else:
                TarungBot.reply_message(
                    event.reply_token, [
                        TextSendMessage(text=result),
                        TextSendMessage(text=(
                            "You've finished the game!\n"
                            + players[player_id].status()))
                    ]
                )

    def bye():
        '''
        Leave a chat room.
        '''
        if isinstance(event.source, SourceGroup):
            quickreply("Leaving group...")
            TarungBot.leave_group(event.source.group_id)

        elif isinstance(event.source, SourceRoom):
            quickreply("Leaving room...")
            TarungBot.leave_room(event.source.room_id)

        else:
            quickreply("I can't leave a 1:1 chat.")

    def ticket_add(item):
        '''
        Add a ticket.
        '''
        tickets = json.loads(dbx.files_download(tickets_path)[1]
                             .content.decode('utf-8'))
        if item in tickets:
            quickreply("Message already exists.")
            return
        if len('num. \n'.join(tickets + [item])) > 2000:
            quickreply(("There are currently too many messages.\n"
                        "Please wait until the developer deletes "
                        "some of them."))
            return

        tickets.append(item)
        dbx.files_upload(json.dumps(tickets).encode('utf-8'), tickets_path,
                         dropbox.files.WriteMode.overwrite)
        quickreply("Message sent!")

    def ticket_get():
        '''
        Send current tickets.
        '''
        tickets = json.loads(dbx.files_download(tickets_path)[1]
                             .content.decode('utf-8'))
        if not tickets:
            quickreply("No messages.")
            return

        current_tickets = "Messages:"
        for num, items in enumerate(tickets):
            current_tickets += "\n{}. {}".format(num+1, items)
        quickreply(current_tickets)

    def ticket_rem(num):
        '''
        Remove a ticket.
        '''
        tickets = json.loads(dbx.files_download(tickets_path)[1]
                             .content.decode('utf-8'))
        if not tickets:
            quickreply("No messages.")
            return
        if num == 'all':
            del tickets[:]
            quickreply("Message list has been emptied.")
        else:
            try:
                num = int(num)
                del tickets[num-1]
            except IndexError:
                quickreply("Message [{}] is not available.".format(num))
            except ValueError:
                quickreply("Wrong format.")
            else:
                quickreply("Message [{}] has been removed.".format(num))
        dbx.files_upload(json.dumps(tickets).encode('utf-8'), tickets_path,
                         dropbox.files.WriteMode.overwrite)

    if text[0] == '/':
        command = text[1:]
        cmd = command.lower().strip()

        if cmd.startswith('about'):
            quickreply(about_msg)

        if cmd.startswith('help'):
            quickreply(help_msg)

        if cmd.startswith('bye'):
            bye()

        if cmd.startswith('start'):
            start(player_id)

        if cmd.startswith('restart'):
            start(player_id, force=True)

        if cmd.startswith('answer '):
            name = command[len('answer '):]
            answer(player_id, name)

        if cmd.split()[0] == 'a':
            name = command[len('a '):]
            answer(player_id, name)

        if cmd.startswith('pass'):
            answer(player_id, 'pass')

        if cmd.startswith('status') and check(player_id):
            quickreply(players[player_id].status())

        if cmd.startswith('msg '):
            item = command[len('msg '):]
            ticket_add(item)

        if cmd.startswith('tix') and event.source.user_id == my_id:
            ticket_get()

        if cmd.startswith('rtix ') and event.source.user_id == my_id:
            item = command[len('rtix '):]
            ticket_rem(item)


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
