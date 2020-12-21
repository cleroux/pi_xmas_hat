import queue
from flask import Flask, render_template, redirect, request, send_file, Response
from sense_hat import SenseHat
from io import StringIO
from os import path
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

app = Flask(__name__)
sense = SenseHat()

sense.low_light = True

colors = {
    "r" : [255, 0, 0], # red
    'o' : [255, 165, 0], # orange
    'y' : [255, 255, 0], # yellow
    'g' : [0, 128, 0], # green
    'b' : [0, 0, 255], # blue
    'i' : [75, 0, 130], # indigo
    'v' : [230, 130, 238], # violet
    'n' : [135, 80, 22], # brown
    'w' : [255, 255, 255], # white
    'e' : [0, 0, 0]  # empty/black
}

with open("images.txt", "r") as f:
    images = f.readlines()

class MessageAnnouncer:
    """
    MessageAnnouncer allows us to send Server-Sent Events (SSE) messages to clients.
    See: https://maxhalford.github.io/blog/flask-sse-no-deps/
    """

    def __init__(self):
        self.listeners = []

    def listen(self):
        self.listeners.append(queue.Queue(maxsize=20))
        return self.listeners[-1]

    def announce(self, msg):
        for i in reversed(range(len(self.listeners))):
            try:
                self.listeners[i].put_nowait(msg)
            except queue.Full:
                del self.listeners[i]

announcer = MessageAnnouncer()

def format_sse(data: str, event=None) -> str:
    """
    Formats a string and an event name in order to follow the event stream convention.
    """
    msg = f'data: {data}\n\n'
    if event is not None:
        msg = f'event: {event}\n{msg}'
    return msg

# Global flag indicates whether an update was made to the pixel display
image_updated = False
message_updated = False

def broadcast_display_updates():
    """
    Scheduled to run once per second, limiting the number of update events
    we can send to clients.
    """
    global image_updated
    global message_updated

    if image_updated:
        pixels = sense.get_pixels()
        svg = render_svg(pixels)
        announcer.announce(msg=format_sse(data='{}'.format(svg)))
        image_updated = False

    if message_updated:
        pixels = sense.get_pixels()

        # Text needs to be rotated -90deg for some reason
        rotated = []
        for x in reversed(range(8)):
            for y in range(8):
                rotated.append(pixels[(y*8)+x])

        svg = render_svg(rotated)
        announcer.announce(msg=format_sse(data='{}'.format(svg)))


scheduler = BackgroundScheduler()
scheduler.add_job(func=broadcast_display_updates, trigger="interval", seconds=1)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/robots.txt")
def robots():
    return send_file("robots.txt")

@app.route("/hacks.html")
def hacks():
    return render_template("hacks.html")

# List of first names that are allowed to log in
names = ["john"]

@app.route("/login", methods=["POST"])
def login():
    name = request.form["name"]
    if name.lower() in names:
        return redirect("/user/" + name)

    return redirect("/")

@app.route("/user/<string:name>")
def home(name):
    return render_template("home.html", name=name.lower().capitalize())

@app.route("/message", methods=["PUT"])
def message():
    # NOTE: Using a global flag is a terrible synchronization mechanism
    # A better solution would be to send messages to a queue so they can
    # be displayed in order.
    # This is a toy designed for kids and I think it will be fun for them to
    # "break" this when they inevitably spam messages.
    global message_updated
    
    msg = request.form["message"]
    message_updated = True
    display_message(msg)
    message_updated = False
    return "OK", 200

@app.route("/image", methods=["PUT"])
def image():
    global image_updated

    img = request.form["image"]

    # Parse ID number
    try:
        i = int(img)
    except ValueError as err:
        return "Invalid ID", 400

    if i < 0 or i > 24:
        return "Invalid ID", 400

    display_image(images[i])
    image_updated = True
    return "OK", 200

@app.route("/image/updates", methods=["GET"])
def image_updates():
    def stream():
        messages = announcer.listen()
        while True:
            msg = messages.get()
            yield msg

    return Response(stream(), mimetype="text/event-stream")

@app.route("/image", methods=["GET"])
def get_display_image():
    pixels = sense.get_pixels()
    svg = render_svg(pixels)
    return Response(svg, mimetype="image/svg+xml")

@app.route("/image/<int:id>", methods=["GET"])
def get_image(id):

    # Parse ID number
    try:
        i = int(id)
    except ValueError as err:
        return "Invalid ID", 400

    if i < 0 or i > 24:
        return "Invalid ID", 400

    # Convert picture string format to pixels
    img = images[i]
    img = img.strip("\n")
    img = img.split(",")
    pixels = []
    for letter in img:
        pixels.append(colors[letter])

    svg = render_svg(pixels)
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Expires"] = "Sun, 10 Jan 2021 00:00:00 GMT"
    return resp

def render_svg(pixels):
    """
    Converts a sense hat pixel picture to SVG format.
    pixels is a list of 64 smaller lists of [R, G, B] pixels.
    """
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80">'

    for y in range(8):
        for x in range(8):
            color = pixels[(y*8)+x]
            if color[0] == 0 and color[1] == 0 and color[2] == 0:
                continue # Skip black pixels so they are rendered transparent
            svg += '<rect x="{x}" y="{y}" width="10" height="10" style="fill:rgb({r},{g},{b})" />'.format(x=x*10, y=y*10, r=color[0], g=color[1], b=color[2])

    svg += '</svg>'
    return svg

def display_image(img):
    img = img.strip("\n")
    img = img.split(",")

    img_list = []
    for letter in img:
        img_list.append(colors[letter])

    sense.set_rotation(180)
    sense.set_pixels(img_list)
    return

def display_message(msg):
    sense.set_rotation(180)
    sense.show_message(msg + " ", scroll_speed=0.2, text_colour=[200, 0, 0])
    return  
