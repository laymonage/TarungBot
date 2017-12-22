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
save_file_path = os.getenv('SAVE_FILE_PATH', None)

my_id = os.getenv('MY_USER_ID', None)
tickets_path = os.getenv('TICKETS_FILE_PATH', None)
tickets = json.loads(dbx.files_download(tickets_path)[1]
                     .content.decode('utf-8'))

about_msg = ("TarungBot\n"
             "---\n"
             "Mengenal Tarung\n"
             "Get to know your Tarung family!\n"
             "---\n"
             "Created by laymonage\n"
             "BIG thanks to: everyone who made game.tarung2017.com "
             "possible, especially Indra (-/\\-)\n"
             "Also thanks to: TARUNG 2017 and all elements of FASILKOM UI\n"
             "\n"
             "Any bugs/suggestions? Use /msg\n"
             "Check out the (ugly) source code at "
             "https://github.com/laymonage/TarungBot\n"
             "\n"
             "Psst, check out @mjb5063s for a multi-purpose bot!")

info_msg = ("How to play:\n"
            "You can start the game with /start\n"
            "Answer questions with /answer, or use /pass when in doubt\n"
            "Start over with /restart\n"
            "\n"
            "Valid answer example:\n"
            "Let name = 'Fatih Al-Mutawakkil'\n"
            "Answer will be exactly correct "
            "if answer.lower() == name.lower()\n"
            "Answer will be correct if "
            "answer contains 'Fat__' or 'Al-________'\n"
            "So answer will be valid as long as at least one word (space-"
            "separated) in answer is in line with 'Fatih Al-Mutawakkil'.\n"
            "like: 'Fati', 'Fatih', 'Fatih A', Al-Mut'\n"
            "If you add a wrong word, so it's e.g. 'Fatih Al-Muttaqin', "
            "you will get a partial score.\n"
            "You can see how this works in the source code.\n"
            "\n"
            "Scoring system:\n"
            "Exactly correct: +5\n"
            "Correct: +3\n"
            "Partially correct: +2\n"
            "Wrong: -1\n"
            "Skipped: 0\n"
            "\n"
            "Since this bot is running on free Heroku dynos, it will sleep "
            "if there's no activity in 30 minutes. "
            "The game is saved every time someone answers 10 questions. "
            "If the bot awakens or the developer updates the bot's code, "
            "it will load the last saved progress.\n"
            "So if you leave the game unfinished with progress % 10 != 0 "
            "for more than 30 minutes, it's recommended to use /start "
            "so the bot will remind you what your current question is.\n"
            "\n"
            "You can send messages to the developer using /msg\n"
            "(don't worry, it's anonymous!)")

help_msg = ("/about : send the about message\n\n"
            "/info : send the info message\n\n"
            "/help : send this help message\n\n"
            "/bye : make me leave this chat room\n\n"
            "/start : start the game\n\n"
            "/restart : restart the game\n\n"
            "/answer <name> : answer the person in the picture with <name>\n\n"
            "/a <name> : short for /answer\n\n"
            "/<name> : (very) short for /answer\n\n"
            "/pass : skip the current person (also /answer pass)\n\n"
            "/p : short for /pass\n\n"
            "/name <name> : set your name to <name> to be shown in the "
            "Leaderboards.\n\n"
            "/stats : show your current game's statistics\n\n"
            "/lead : see the Leaderboards\n\n"
            "/msg <message> : send <message> to the developer")


class Player:
    '''
    A player
    '''
    guys = sorted([guy.name.replace('.jpg', '')
                   for guy in dbx.files_list_folder(game_data_path + '/male')
                   .entries])
    gals = sorted([gal.name.replace('.jpg', '')
                   for gal in dbx.files_list_folder(game_data_path + '/female')
                   .entries])

    def __init__(self, name='Anonymous', pick='', progress=None, data=None):
        self.name = name
        self.pick = pick
        if progress is None:
            self.progress = Player.guys + Player.gals
        else:
            self.progress = progress
        if data is None:
            self.data = {'exact': 0, 'correct': 0, 'partial': 0,
                         'wrong': 0, 'skipped': 0, 'count': 0,
                         'score': 0, 'high_score': 0}
        else:
            self.data = data

    def finished(self):
        '''
        Check if a player has finished their game.
        '''
        if self.progress:
            return False
        return True

    def next_link(self, repick=False):
        '''
        Get next random link.
        '''
        if not repick:
            self.pick = random.choice(self.progress)
        if self.pick in Player.guys:
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
        if self.pick in Player.guys:
            pronoun = ('He', 'him')
        else:
            pronoun = ('She', 'her')
        specific = True
        correct = False
        partial = False

        if name.lower() == 'pass':
            msg = ("{} is {}. Remember {} next time!"
                   .format(pronoun[0], self.pick, pronoun[1]))
            self.data['skipped'] += 1

        elif name.lower() == self.pick.lower():
            msg = ("Wow, that's exactly right! {} is {}."
                   .format(pronoun[0], self.pick))
            self.data['exact'] += 1

        else:
            for word in name.title().split():
                if (word in 'Muhammad' or
                        word in 'Muhamad' or
                        word in 'Naufal' or
                        len(word) < 3):
                    if (not partial and word not in self.pick and
                            correct or word == name.title().split()[0]
                            and len(name.title().split()) > 1):
                        partial = True
                    if not correct and not partial:
                        specific = False
                        msg = ("Please be more specific. Try again!")
                elif word in self.pick:
                    specific = True
                    correct = True
                    if not partial:
                        msg = ("You are correct! {} is {}."
                               .format(pronoun[0], self.pick))
                    elif partial:
                        msg = ("You are partially correct! {} is actually {}, "
                               "not {}."
                               .format(pronoun[0], self.pick, name.title()))
                else:
                    specific = True
                    partial = True
                    if correct:
                        msg = ("You are partially correct! {} is actually {}, "
                               "not {}."
                               .format(pronoun[0], self.pick, name.title()))

            if specific and not correct:
                msg = ("You are wrong! {} is {}. Remember {} next time!"
                       .format(pronoun[0], self.pick, pronoun[1]))
                self.data['wrong'] += 1
            if specific and correct and partial:
                self.data['partial'] += 1
            if specific and correct and not partial:
                self.data['correct'] += 1
        if specific:
            self.progress.remove(self.pick)
            self.data['count'] += 1
            self.data['score'] = (5*self.data['exact'] +
                                  3*self.data['correct'] +
                                  2*self.data['partial'] -
                                  1*self.data['wrong'])
            if self.data['score'] > self.data['high_score']:
                self.data['high_score'] = self.data['score']
        return msg

    def stats(self):
        '''
        Return a player's current game statistics.
        '''
        return ("{}/{} persons.\n"
                "Exact: {} ({:.2f}%)\n"
                "Correct: {} ({:.2f}%)\n"
                "Partial: {} ({:.2f}%)\n"
                "Wrong: {} ({:.2f}%)\n"
                "Skipped: {} ({:.2f}%)\n"
                "Current Score: {}\n"
                "Highest Score: {}\n"
                "Name: {}"
                .format(len(Player.guys+Player.gals) - len(self.progress),
                        len(Player.guys+Player.gals),
                        self.data['exact'],
                        self.data['exact']/len(Player.guys+Player.gals)*100,
                        self.data['correct'],
                        self.data['correct']/len(Player.guys+Player.gals)*100,
                        self.data['partial'],
                        self.data['partial']/len(Player.guys+Player.gals)*100,
                        self.data['wrong'],
                        self.data['wrong']/len(Player.guys+Player.gals)*100,
                        self.data['skipped'],
                        self.data['skipped']/len(Player.guys+Player.gals)*100,
                        self.data['score'],
                        self.data['high_score'],
                        self.name))

    def toJSON(self):
        '''
        Return an instance's JSON-compatible dictionary representation.
        '''
        stats = {'name': self.name, 'pick': self.pick,
                 'progress': self.progress, 'data': self.data}
        return stats


players = json.loads(dbx.files_download(save_file_path)[1]
                     .content.decode('utf-8'))
for each in players:
    players[each] = Player(name=players[each]['name'],
                           pick=players[each]['pick'],
                           progress=players[each]['progress'],
                           data=players[each]['data'])


@app.route("/callback", methods=['POST'])
def callback():
    '''
    Webhook callback function
    '''
    # Get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # Get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # Handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


# pylint: disable=too-many-statements
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
        players[user_id] = Player()

    def can_start_game(user_id):
        '''
        Check if a user can start the game.
        '''
        if user_id in players:
            if not players[user_id].finished():
                return False
        return True

    def send_question(user_id, prev=None, reask=False):
        '''
        Send a question
        '''
        if not prev:
            content = [TextSendMessage(text="Starting game...")]
        else:
            content = [TextSendMessage(text=prev)]
        link = players[user_id].next_link(reask)
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
            msg = ("Your game is still in progress.\n"
                   "Use /restart to restart your progress.\n"
                   "Here's your current question:")
            send_question(user_id, prev=msg, reask=True)

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
                            + players[player_id].stats()))
                    ]
                )
                players[user_id].data['count'] = 10
            if players[user_id].data['count'] >= 10:
                players[user_id].data['count'] = 0
                dbx.files_upload(json.dumps({each: players[each].toJSON()
                                             for each in players}, indent=4)
                                 .encode('utf-8'), save_file_path,
                                 dropbox.files.WriteMode.overwrite)

    def set_name(user_id, name):
        '''
        Change the name to be shown in Leaderboards.
        '''
        if check(user_id):
            if len(name) <= 20:
                if '(group)' not in name:
                    players[user_id].name = name
                    quickreply("Name set to {}.".format(name))
                else:
                    quickreply("You shouldn't put (group) in your name.")
            else:
                quickreply(("Too long.\n"
                            "Name should consist of 20 characters or less."))

    def see_leaderboards():
        '''
        Send current Leaderboards.
        '''
        msg = 'Leaderboards:'
        lb = []
        for player in players:
            group = False if player[0] == 'U' else True
            lb.append([players[player].data['high_score'],
                       players[player].name, group])
        lb.sort(reverse=True)
        i = 0
        for item in lb[:10]:
            if item[2]:
                msg += '\n{}. {} (group) [{}]'.format(i+1, item[1], item[0])
            else:
                msg += '\n{}. {} [{}]'.format(i+1, item[1], item[0])
            i += 1
        quickreply(msg)

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
        if item in tickets:
            quickreply("Message already exists.")
            return
        if len('num. \n'.join(tickets + [item])) > 2000:
            quickreply(("There are currently too many messages.\n"
                        "Please wait until the developer deletes "
                        "some of them."))
            return

        tickets.append(item)
        dbx.files_upload(json.dumps(tickets, indent=4).encode('utf-8'),
                         tickets_path, dropbox.files.WriteMode.overwrite)
        quickreply("Message sent!")

    def ticket_get():
        '''
        Send current tickets.
        '''
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
        dbx.files_upload(json.dumps(tickets, indent=4).encode('utf-8'),
                         tickets_path, dropbox.files.WriteMode.overwrite)

    if text[0] == '/':
        command = text[1:]
        cmd = command.lower().strip()

        if cmd.startswith('about'):
            quickreply(about_msg)

        elif cmd.startswith('info'):
            quickreply(info_msg)

        elif cmd.startswith('help'):
            quickreply(help_msg)

        elif cmd.startswith('bye'):
            bye()

        elif cmd.startswith('start'):
            start(player_id)

        elif cmd.startswith('restart'):
            start(player_id, force=True)

        elif cmd.startswith('answer '):
            name = command[len('answer '):]
            answer(player_id, name)

        elif cmd.split()[0] == 'a':
            name = command[len('a '):]
            answer(player_id, name)

        elif cmd.startswith('pass') or cmd.split()[0] == 'p':
            answer(player_id, 'pass')

        elif cmd.startswith('name '):
            name = command[len('name '):]
            set_name(player_id, name)

        elif cmd.startswith('stats') and check(player_id):
            quickreply(players[player_id].stats())

        elif cmd.startswith('lead'):
            see_leaderboards()

        elif cmd.startswith('msg '):
            item = command[len('msg '):]
            ticket_add(item)

        elif cmd.startswith('tix') and event.source.user_id == my_id:
            ticket_get()

        elif cmd.startswith('rtix ') and event.source.user_id == my_id:
            item = command[len('rtix '):]
            ticket_rem(item)

        elif cmd == 'tarung':
            quickreply('\U00100027 2017! \U001000a4')

        elif cmd == 'tarung2017':
            quickreply(("Serang! \U001000a4\n"
                        "Terjang! \U00100064\n"
                        "Menang! \U00100073"))

        else:
            answer(player_id, command)


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
