import argparse
from configparser import SafeConfigParser
import getpass
import logging
import os
import pathlib
import stashy
import sys


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)


def setup_args(argv):
    conf_parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    conf_parser.add_argument(
        "-c", "--conf_file",
        help="Specify config file. Arguments specified in config file will be "
             "overridden if they're passed to the command.",
        metavar="FILE",
    )
    args, remaining_argv = conf_parser.parse_known_args()
    defaults = {
        "gitea_http_base": "",
        "gitea_ssh_base": "",
        "gitea_api_key": "",
        "gitea_org": "",
        "bitbucket_http_base": "",
        "bitbucket_username": "",
        "bitbucket_project": "",
        "gitmodule_mappings": "",
        "working_dir": "",
        "push": False,
    }
    if args.conf_file is not None:
        config = SafeConfigParser()
        config.read([args.conf_file])
        defaults.update(dict(config.items("DEFAULT")))
    parser = argparse.ArgumentParser(
        parents=[conf_parser],
    )
    parser.set_defaults(**defaults)
    parser.add_argument(
        "--gitea_http_base",
        help="Base HTTP URL of Gitea instance, for interacting with API",
        metavar="URL",
    )
    parser.add_argument(
        "--gitea_ssh_base",
        help="Base SSH URL of Gitea instance, for interacting with repositories",
        metavar="URL",
    )
    parser.add_argument(
        "--gitea_api_key",
        help="Gitea API Key",
        metavar="KEY",
    )
    parser.add_argument(
        "--gitea_org",
        help="Organization in Gitea to move repositories to",
        metavar="NAME",
    )
    parser.add_argument(
        "--bitbucket_http_base",
        help="Base HTTP URL of Bitbucket/Stash instance, for interacting with API",
        metavar="URL",
    )
    parser.add_argument(
        "--bitbucket_username",
        help="Username to access bitbucket API",
        metavar="USERNAME",
    )
    parser.add_argument(
        "--bitbucket_project",
        help="Bitbucket/Stash project to move repositories from",
        metavar="PROJECT_KEY",
    )
    parser.add_argument(
        "--gitmodule_mappings",
        help="A list of 'old new' replacements to perform on .gitmodule "
             "files. One pair, separated by a space, per line.",
        metavar="OLD NEW\\n...",
    )
    parser.add_argument(
        "--working_dir",
        help="Working directory for checking out git repositories.",
        metavar="PATH",
    )
    parser.add_argument(
        "--push",
        help="Push all branches and tags to new origin.",
        action="store_true",
    )
    args = parser.parse_args(remaining_argv)
    return args


def process_repos(stash, project_key, working_folder, gitea_ssh_base, gitea_org, gitmodule_mappings):
    logging.info("making sure working folder exists: "+working_folder)
    pathlib.Path(working_folder).mkdir(parents=True, exist_ok=True)

    paths = []
    for repo in stash.projects[project_key].repos.list():
        if "MOVED" in repo["name"]:
            logging.info("skipping because MOVED: "+repo["name"])
            continue

        # get first ssh url
        for url in repo["links"]["clone"]:
            if url["name"] != "ssh":
                continue
            repo_ssh_url = url["href"]
            break

        # GET OR UPDATE
        logging.info("cloning "+repo["name"])
        checkout_folder = os.path.join(working_folder, repo["name"])
        if os.path.exists(checkout_folder):
            try:
                os.system("cd \""+checkout_folder+"\" && git pull --rebase")
            except Exception:
                logging.error("couldn't pull: "+checkout_folder)
                continue
        else:
            try:
                os.system("cd \""+working_folder+"\" && git clone "+repo_ssh_url)
            except Exception:
                logging.error("couldn't clone: "+repo["name"])
                continue

        # GET ALL BRANCHES
        logging.info("getting all branches for "+repo["name"])
        try:
            os.system(
                "cd \""+checkout_folder+"\" && "
                "for branch in `"
                "git branch -a "
                "| grep remotes "
                "| grep -v HEAD "
                "| grep -v master`; "
                "do git branch --track ${branch#remotes/origin/} $branch; "
                "done")
        except Exception:
            logging.error("couldn't checkout branches: "+repo["name"])
            continue

        # UPDATE REMOTES
        logging.info("updating remotes for "+repo["name"])
        try:
            gitea_url = gitea_ssh_base + gitea_org + "/" + repo["name"] + ".git"
            os.system("cd \""+checkout_folder+"\" && git remote set-url origin \""+gitea_url+"\"")
        except Exception:
            logging.error("couldn't set origins: "+repo["name"])
            continue

        # UPDATE GITMODULES
        if os.path.exists(os.path.join(checkout_folder, ".gitmodules")):
            with open(os.path.join(checkout_folder, ".gitmodules")) as fin:
                txt = fin.read()
                for mapping in gitmodule_mappings:
                    txt = txt.replace(mapping[0], mapping[1])

            with open(os.path.join(checkout_folder, ".gitmodules"), 'w') as fout:
                fout.write(txt)

            os.system("cd \""+checkout_folder+"\" && git commit -am \"update gitmodules\"")

        paths.append((repo["name"], checkout_folder))

    return paths


def push_all(paths, gitea_http_base, gitea_api_key, gitea_org):
    logging.info("Pushing repositories to new remotes")
    for reponame, checkout_folder in paths:
        logging.info("creating repo on Gitea, if missing: "+reponame)
        os.system("curl -X POST '" + gitea_http_base + "api/v1/org/" + gitea_org +
                  "/repos?token=" + gitea_api_key + "' "
                  + "-H 'accept: application/json' "
                  + "-H 'Content-Type: application/json' "
                  + "-d '{\"name\": \"" + reponame + "\", \"private\": true}' ")
        logging.info("pushing all branches and tags: "+reponame)
        os.system("cd \"" + checkout_folder + "\" && git push --all && git push --tags")


def main(argv=None):
    if argv is None:
        argv = sys.argv
    args = setup_args(argv)

    bitbucket_pass = getpass.getpass(
        "Bitbucket/Stash password for '{user}': ".format(user=args.bitbucket_username)
    )
    logging.info("connecting to bitbucket/stash...")
    stash = stashy.connect(
        args.bitbucket_http_base,
        args.bitbucket_username,
        bitbucket_pass
    )

    gitmodule_mappings = []
    for line in args.gitmodule_mappings.splitlines():
        if len(line.strip()) <= 0:
            continue
        parts = line.split(' ')
        gitmodule_mappings.append((parts[0], parts[1]))

    paths = process_repos(
        stash,
        args.bitbucket_project,
        args.working_dir,
        args.gitea_ssh_base,
        args.gitea_org,
        gitmodule_mappings,
    )
    if args.push:
        push_all(
            paths,
            args.gitea_http_base,
            args.gitea_api_key,
            args.gitea_org,
        )
    else:
        logging.info("skipping push")
