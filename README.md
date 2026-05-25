# sugarcube_bazel

Bazel rules for SugarCube games.

## Overview

This repository contains a set of simple Bazel rules that can be used to create
[SugarCube](https://www.motoslave.net/sugarcube/2/docs/) games out of several
separate passage files and assets, and organize them into libraries of passages.

[Bazel](https://bazel.build/) is a professional, open-source build system that
is written by Google and is widely used in the software industry. It can be used
to create build graphs (nodes are build steps, and edges are all files flowing
in and out of each step) and execute them in a hermetic and reproducible manner
that also minimizing re-building, through caching and hashing of build artifacts.

Needless to say, most of Bazel's power is overkill for SugarCube games, but it's
just a very flexible system to use, with the main benefit that rather than writing
large monolithic games, through these Bazel rules passages, each
written in a single file, can be grouped into small libraries and linked to the
specific assets they use (media, images, videos, etc.). Then, top-level games can
be created by grouping together (as dependencies) the libraries of passages it
uses. Bazel takes care of producing to complete list of passages and assets,
without duplicates, and producing a deployment of the game's top-level `index.html`
file and a directory containing all needed assets (nothing more, nothing less).

## Getting started

Familiarity with Bazel is preferable, but the following guide should be sufficient
to get started, even without being familiar with it.

### Requirements

 - Bash environment: MacOS and Linux should work out of the box. Windows apparently
   could also work with a bash environment such MSYS2, but not tested. See Bazel
   documentation on that.
 - Bazel: [See Bazel's Getting Started Guide](https://bazel.build/start)
 - Tools (to install by whatever method is appropriate):
   - `GNU/coreutils` for basic commands (should be part of any system with bash)
   - `sed` for file substitutions (should be part of any system with bash)
   - `jq` for json parsing
   - `html-xml-utils` for html parsing and query via `hxselect` (optional)
   - `git` for Bazel to be able to download / clone this repository

### Importing sugarcube_bazel into a Bazel project

A Bazel project starts off as a `MODULE.bazel` file in the top-level directory of
the project. When using `sugarcube_bazel`, it should, at minimum, contain the following:

```py
# In MODULE.bazel:
module(name = "my_game_project")

git_repository = use_repo_rule("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

bazel_dep(name = "bazel_skylib", version = "1.9.0")
bazel_dep(name = "rules_shell", version = "0.8.0")

# sugarcube_bazel
git_repository(
    name = "sugarcube_bazel",
    branch = "main",
    remote = "https://github.com/somebody-else-sg/sugarcube_bazel.git",
)

```

The `module(name = "my_game_project")` is declaring your game project with whatever name
you want to give it. Note that this is the overall project which could contain many different
games. In fact, one benefit of `sugarcube_bazel` is being able to create multiple games
that share many passages and assets, but still produce standalone deployments.

The lines with `bazel_skylib` and `rules_shell` simply import dependencies of `sugarcube_bazel`.
And, of course, the `git_repository` statement imports `sugarcube_bazel` itself. Note that
the `branch = "main"` line could be replaced by either `commit = "<commit hash>"` or `tag = "<tag name>"`
to point to a particular commit or tag rather than the latest state of the main branch.

### Defining a sugarcube_story target

Bazel, like most build systems, works by defining build "targets", usually on a per-directory
basis. In Bazel, any file called `BUILD.bazel` in a directory is interpreted as defining such
targets, and the directories are searched down recursively. Typically, at the top-level, you
would create a `sugarcube_story` target which is going to be the top-level target use to
build your SugarCube game. This is how a top-level `BUILD.bazel` file might look like:

```py
# In BUILD.bazel:
load('@sugarcube_bazel//:defs.bzl', 'sugarcube_story')

package(default_visibility = ["//:__subpackages__"])

filegroup(
    name = "user_scripts",
    srcs = ["user_script.html"],
)

filegroup(
    name = "user_stylesheet",
    srcs = ["user_stylesheet.html"],
)

sugarcube_story(
  name = "my_story",
  title = "My Story Title",
  ifid = "<insert IFID number>",
  user_stylesheet = ":user_stylesheet",
  user_script = ":user_scripts",
  deps = [
    "//passages:start",
    "//passages/my_story", # Game-specific libraries
  ],
)
```

The `sugarcube_story` rule expects a few parameters:

 - `name`: The name of the target (can be anything, it will not appear in the output).
 - `title`: The title of the story as it will appear in places such as the title-bar
   of the browser's tab.
 - `ifid`: The IFID (Interactive Fiction IDentifier) number assigned to this SugarCube
   game. See [TADS.org](https://www.tads.org/ifidgen/ifidgen).
 - `user_stylesheet`: The CSS stylesheets, i.e., html files containing only a block starting
   with `<style role="stylesheet" id="<some name>" type="text/twine-css">`,
   containing user-defined stylesheets for your story. Note that there can be multiple files.
 - `user_scripts`: The user scripts, i.e., html files containing only a block starting
   with `<script role="script" id="<some name>" type="text/twine-javascript">`,
   containing user-defined javascript for your story. Note that there can be multiple files.
 - `deps`: The list of libraries of passages that the story depends on. See the next
   section on definining libraries.
 - `format` (optional): The Sugarcube format file to use, by default it uses
   `@sugarcube_bazel//formats/sugarcube-2.37.3:format`, but other formats are
   available and new ones can be defined with the `sugarcube_format` rule.

To build the story, invoke Bazel as follows from the top-level directory:

```sh
bazel build //:my_story
```

If the story is defined further down in a sub-directory, it would be invoked with the
target name like `//some/path:my_story`.

After building the story, the `index.html` file will be generated in the build directory.
Bazel should print out that path, it should be `bazel-bin/my_story/index.html`. In that
build directory, alongside `index.html`, you should also find all the assets of all the
passages that were used to create the story (as symbolic links, not copies!). In other
words, the build folder should contain all the files needed to deploy/serve the game.

### Defining sugarcube_library targets

To create libraries of passages, you use the `sugarcube_library` rule, which takes
the following arguments:

 - `name`: The name of the target (how other libraries or story targets refer to it).
 - `srcs`: The set of source files, aka passages, for this library. Passages are just
   plain text files, with the file extension `.scp` (Sugarcube passage) and start
   with `/* PASSAGE: Passage Id */` where `Passage Id` is the unique name of the
   passage (i.e., the one used in links, etc.). After that first line, the rest is
   simply the body of the passage in question.
 - `tags` (optional): The set of tags to apply to the passages, see sugarcube docs
   for the usage of tags. Mainly, the `widget` tag is used to create widget passages.
 - `deps` (optional): The set of targets (libraries of passages) that this library
   depends on. The dependencies need to form an acyclic graph containing all passages
   that ultimately are needed for the complete game. Generally, a library would
   depend on libraries containing the passages that are directly linked to from its
   own passages.
 - `data` (optional): The set of files that this library will need at "run-time". These
   are the game assets such as images, videos and audio files needed when serving the
   game to players. These will appear in the build directory with the same directory
   structure as they appear in the source directory.

Here is an example `BUILD.bazel` file defining some libraries for a basic game, with
the elements explained in in-line comments:

```py
load('@sugarcube_bazel//:defs.bzl', 'sugarcube_library')

package(default_visibility = ["//:__subpackages__"])

# Define a new sugarcube library for widgets.
sugarcube_library(
  name = "widgets",
  tags = ["widget"],  # Tag these passages as containing widgets (aka scripts).
  srcs = [
    "media_coding.scp", # List of passages
    "link_coding.scp",
    "stats_coding.scp",
  ],
)

# Define a new sugarcube library for game locations menu.
sugarcube_library(
  name = "locations",
  srcs = [
    "locations.scp", # A passage listing links to locations to visit.
  ],
  deps = [
    "//passages/home", # Depend on 'home' passages, since locations link to it.
    "//passages/mall", # Depend on 'mall' passages, since locations link to it.
  ],
)

# Define a group of files for the various assets used in top-level passages.
filegroup(
  name = "start_data",
  srcs = glob(["*.jpg"]) # Use glob pattern to get all jpg files in current directory.
    + ["start_animation.mp4", "moving_icon.gif"], # Add a few other files.
)

# Define a new sugarcube library for core game passages.
sugarcube_library(
  name = "start",
  srcs = [
    "start.scp",          # The special 'Start' passage.
    "stats.scp",          # A passage for displaying character stats.
    "story_author.scp",   # The story author display passage.
    "story_caption.scp",  # The story caption display passage.
    "story_init.scp",     # The special 'StoryInit' passage that initializes all variables.
    "story_menu.scp",     # The story side-bar menu passage.
    "story_subtitle.scp", # The story sub-title passage.
  ],
  deps = [
    ":widgets",   # Bring in the widgets / scripts for this game.
    ":locations", # After the start, we go to the locations menu, so, depend on that.
  ],
  data = [
    ":start_data", # Core game passages need the 'start_data' assets.
  ],
)
```

That's pretty much all there is to it. There are probably some Bazel-specific knowledge missing
or assumed from this quick guide, see the Bazel docs for more info.

## License

BSD 2-Clause License

Copyright (c) 2026, SomebodyElse

## Disclaimer

This is provided 'as is', do not expect any level of maintenance or response to
issues or pull requests. This is mainly released because I made this and found it
very useful (and miles better than anything else that I know of to create SugarCube or
Twine games, like twine, tweego, etc.), and I just wanted to share it.

