# Markdownload
Intended for automated markdown snippet insertion based on github webhooks.

This simple flask-based app will listen for commits pushed to a github repository and then programmatically (based on a config file) will 
check for changes to tracked files and templates.

## Installation
1. Ensure git is installed and has your credentials set up.
2. Copy the markdownload.py and requirements.txt files to the desired location.
3. Run `pip install -r requirements.txt`
4. Add a webhook to you Github repository which sends push payloads in the `application/json` format, 
this should point to a valid ip/domain and port where you will be hosting this webhook.

## Usage
### Template and file creation (see the `sample` directory for examples)
Inside your Github repository do the following:

Create whatever file you want automatically updated and insert template tags as desired.
These tags are in the form: `{{ my_template.md }}`.
You must then create the template file following the same path as inserted (i.e. in this case it would be my_template.md).
These templates can contain any arbitrary string of text. 

### Configuration (see the `config.json` file for an example)
The configuration must follow the JSON format.
First add the `working_dir` key, this should point to the working directory for which paths refer to for compilations.
Then add the `repo_url` key, this should point to the git url for the repository to track (where you added your webhook).
Finally configure your tracked files. 
These are an array under the 'tracked' key.
Each entry is an object with the keys 'input', 'output', and 'templates'.
`input` refers to the path relative to `working_dir` which needs to be "compiled".
`output` refers to the path relative to `working_dir` which is where compiled files get placed.
`templates` is an array with directories pointing to templates or direct template paths. 
This "exposes" those templates for use in compilation.

### Starting the server
Simply run `python3 markdownload.py [--port 80] [--config config.json]`
or if you just want to test the output, `python3 markdownload.py --compile [--config config.json]`
