import json
import os
from subprocess import call
from glob import glob
from itertools import chain
import re

from flask import Flask, request, abort

app = Flask(__name__)
app.debug = os.environ.get('DEBUG') == 'true'

# matches "{{ filepath }}"
path_pattern = re.compile(r'([\w\d\\/]+)(\.)([\w\d\\/]+)')
import_pattern = re.compile(r'(\{\{)(\s)%s(\s)(\}\})' % path_pattern.pattern)  # I know, this is crappy regex


def md_filter(x): return ".md" in x.lower() or ".markdown" in x.lower()


def safe_glob(x):
    globbed = glob(x)
    if len(globbed) == 0:
        return [x]
    else:
        return globbed


@app.route("/", methods=['GET', 'POST'])
def index():
    print("Received webhook...")
    if request.method == 'GET':
        return "Yes I am alive"
    elif request.method == 'POST':
        event = request.headers.get('X-GitHub-Event')
        if event == 'ping':
            return json.dumps({'msg': 'hello world'})
        elif event == 'push':
            print("Push received! Checking if recompilation is needed...")
            payload = json.loads(request.data)
            changed = set()
            for commit in payload['commits']:
                changed |= set([x for x in commit['added'] if md_filter(x)])
                changed |= set([x for x in commit['removed'] if md_filter(x)])
                changed |= set([x for x in commit['modified'] if md_filter(x)])
            tracking = set()
            for tracked in config['tracked']:
                tracking.add(tracked['input'])
                tracking |= set(tracked['templates'])
            if len(changed) != 0 and len(changed ^ set(chain(*[safe_glob(transform_template_path(x, config['repo_dir'])) for x in tracking]))) != 0:  # Only recompile on changes to markdown files
                print("Recompilation needed!")
                update()
            else:
                print("Recompilation not needed!")
            return "OK"
        else:
            abort(403)
    else:
        abort(403)


def update():
    print("Updating the git repository...")
    if not os.path.exists(config['repo_dir']):
        call("git clone %s %s" % (config['repo_url'], config['repo_dir']), shell=True)
    call("git fetch && git pull", shell=True)
    parse_and_compile()
    print("Preparing to push changes...")
    call("git add .", shell=True)
    call("git commit -m \"[Automated] Update markdown files\"", shell=True)
    print("Pushing...")
    call("git push", shell=True)
    print("Done!")


def transform_template_path(path, cwd):
    return os.path.abspath(sanitize_join(cwd, path))


def parse_and_compile():
    print("Parsing configuration...")
    cwd = config['repo_dir']
    for tracked in config['tracked']:
        compile_md(tracked['input'], tracked['output'], set(chain(*[safe_glob(transform_template_path(x, cwd)) for x in tracked['templates']])), cwd)


def sanitize_join(dir1: str, dir2: str) -> str:
    if dir2.startswith(dir1):
        return dir2

    sdir1 = dir1.replace(os.altsep, os.sep)
    sdir2 = dir2.replace(os.altsep, os.sep)
    if sdir2.startswith(os.sep):
        sdir2 = sdir2.replace(os.sep, '', 1)
    return os.path.join(sdir1, sdir2)


def find_template(loc, templates, default='ERROR'):
    for template in templates:
        if template.endswith(loc):
            with open(template, 'r') as t:
                return t.read()
    return default


def compile_md(input, output, templates, cwd):
    input = sanitize_join(cwd, input)
    output = sanitize_join(cwd, output)
    templates = [sanitize_join(cwd, x) for x in templates]

    print("Compiling %s -> %s..." % (input, output))
    print("(Using templates: %s)" % ", ".join(templates))

    if os.path.exists(output):
        os.remove(output)

    with open(input, 'r') as i, open(output, 'w') as o:
        for line in i:
            matched_strings = import_pattern.findall(line)
            for matched in matched_strings:
                total_str = "".join(matched)
                template_name = "".join(path_pattern.findall(total_str)[0])
                template = find_template(template_name, templates)
                line = line.replace(total_str, template, 1)
            o.write(line)


if __name__ == "__main__":
    global config
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Runs Markdownload. (No-args simply runs the webhook server using the ./config.json file)")
    parser.add_argument('--config', action='store', default="config.json", help="The location of the config json")
    parser.add_argument('--compile', action='store_true', default=False, help="Simply compiles the output markdown files")
    parser.add_argument('--port', action='store', type=int, default=80, help="The port of the webserver")

    args = parser.parse_args()

    print("Reading %s..." % args.config)
    if os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config = json.load(f)

    if args.compile:
        parse_and_compile()
    else:
        print("Starting the webserver...")
        app.run(host='0.0.0.0', port=args.port)
