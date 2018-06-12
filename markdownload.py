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
PATH_PATTERN = re.compile(r'([\w\d\\/]+)(\.)([\w\d\\/]+)')
IMPORT_PATTERN = re.compile(r'(\{\{)(\s)%s(\s)(\}\})' % PATH_PATTERN.pattern)  # I know, this is crappy regex

PARTIAL_SNIPPET_START = '%STARTSNIPPET%'
PARTIAL_SNIPPET_END = '%ENDSNIPPET%'

MD_CODEBLOCK_EXCHANGER = {'py': 'python', 'kt': 'kotlin'}


def md_or_config_filter(x): return ".md" in x.lower() or ".markdown" in x.lower() or x in config_path


def safe_glob(x):
    globbed = glob(x)
    if len(globbed) == 0:
        return [x]
    else:
        return globbed


@app.route("/", methods=['GET', 'POST'])
def index():
    global config
    global config_path
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
                if '[automated]' in commit['message'].lower(): # Ignore automated commits
                    continue
                changed |= set([x for x in commit['added'] if md_or_config_filter(x)])
                changed |= set([x for x in commit['removed'] if md_or_config_filter(x)])
                changed |= set([x for x in commit['modified'] if md_or_config_filter(x)])
            changed_config_test = [x for x in changed if x in config_path]
            if len(changed_config_test) != 0:
                print("Config may have been changed! Reloading it...")
                with open(args.config, 'r') as f:
                    config = json.load(f)
            tracking = set()
            for tracked in config['tracked']:
                tracking.add(tracked['input'])
                tracking |= set(tracked['templates'])
            if len(changed) != 0 and len(changed ^ set(chain(*[safe_glob(transform_template_path(x, config['working_dir'])) for x in tracking]))) != 0:  # Only recompile on changes to markdown files
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
    global amend
    print("Updating the git repository...")
    if not os.path.exists(config['working_dir']):
        call("git clone %s" % config['repo_url'], shell=True)
    call("git fetch && git pull", shell=True)
    parse_and_compile()
    print("Preparing to push changes...")
    call("git add .", shell=True)
    if amend:
        call("git commit --amend --no-edit", shell=True)
    else:
        call("git commit -m \"[Automated] Update markdown files\"", shell=True)
    print("Pushing...")
    call("git push%s" % "" if not amend else " -f", shell=True)
    print("Done!")


def transform_template_path(path, cwd):
    return os.path.abspath(sanitize_join(cwd, path))


def parse_and_compile():
    print("Parsing configuration...")
    cwd = config['working_dir']
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


def scan_for_template(string, extension):
    if PARTIAL_SNIPPET_START in string:
        assert PARTIAL_SNIPPET_END in string
        assert string.count(PARTIAL_SNIPPET_START) == 1
        collected = []
        is_collecting = False
        for line in string.splitlines():
            if is_collecting:
                if PARTIAL_SNIPPET_END in line:
                    if "md" in extension.lower() or "markdown" in extension.lower() or "txt" in extension.lower():
                        return "\n".join(collected)  # Don't wrap markdown in code blocks
                    else:
                        return "```%s\n%s\n```" % (MD_CODEBLOCK_EXCHANGER.get(extension, extension), "\n".join(collected))
                else:
                    collected.append(line)
            else:
                if PARTIAL_SNIPPET_START in line:
                    is_collecting = True
    else:
        return string


def find_template(loc, templates, default='ERROR'):
    for template in templates:
        if template.endswith(loc):
            with open(template, 'r') as t:
                return scan_for_template(t.read(), os.path.splitext(template)[1].lstrip('.'))
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
            matched_strings = IMPORT_PATTERN.findall(line)
            for matched in matched_strings:
                total_str = "".join(matched)
                template_name = "".join(PATH_PATTERN.findall(total_str)[0])
                template = find_template(template_name, templates)
                line = line.replace(total_str, template, 1)
            o.write(line)


if __name__ == "__main__":
    global config
    global config_path
    global amend
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Runs Markdownload. (No-args simply runs the webhook server using the ./config.json file)")
    parser.add_argument('--config', action='store', default="config.json", help="The location of the config json")
    parser.add_argument('--compile', action='store_true', default=False, help="Simply compiles the output markdown files")
    parser.add_argument('--port', action='store', type=int, default=80, help="The port of the webserver")
    parser.add_argument('--amend', action='store_true', default=False, help="Automated commits amend to the previous one instead of making a new commit.")

    args = parser.parse_args()

    amend = args.amend

    print("Reading %s..." % args.config)
    config_path = args.config
    if os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config = json.load(f)

    if args.compile:
        parse_and_compile()
    else:
        print("Starting the webserver...")
        app.run(host='0.0.0.0', port=args.port)
