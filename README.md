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
that also minimizes re-building, through caching and hashing of build artifacts.

Needless to say, most of Bazel's power is overkill for SugarCube games, but it's
just a very flexible system to use, with the main benefit that rather than writing
large monolithic games, through these Bazel libraries of passages, each
written in a single file, can be grouped into small libraries and linked to the
specific assets they use (media, images, videos, etc.). Then, top-level games can
be created by grouping together (as dependencies) the libraries of passages it
uses. Bazel takes care of producing a complete list of passages and assets,
without duplicates, and producing a deployment of the game's top-level `index.html`
file and a directory containing all needed assets (nothing more, nothing less).

See the [Getting started](#getting-started) section to get started on using
Bazel to build your Sugarcube story. As a lighter-weight option, you might find
some of the standalone scripts useful too.

## Standalone scripts

There are a few useful standalone Python scripts in this repo that can be used
in any project, without needing Bazel and a full setup.

### Checking Sugarcube stories

The `check_sugarcube_macros.py` script can be used to check for valid uses of
macros inside the passages of a Sugarcube story. See the [Checks section](#checks)
below for more information about the checks. To check a story (e.g., `my_story.html`)
for consistent usage of macros, use this command:

```sh
./scripts/check_sugarcube_macros.py -p my_story.html -m ./scripts/sugarcube_macro_list.json
```

**NOTE**: On some systems, you might have to use `python3 ./scripts/check_sugarcube_macros.py`
instead to launch the Python script (most environments should respect the "shebang",
but some weird systems don't, like Windows).

The script can also accept a set of `.tw` or `.twee` files instead of the final html:

```sh
./scripts/check_sugarcube_macros.py -p p1.tw p2.tw .. pn.tw -m ./scripts/sugarcube_macro_list.json
```

The `sugarcube_macro_list.json` file contains a list of all built-in Sugarcube macros.
To allow the checker to also consider your own macros (either created with `widget` or
added via `Macro.add` in Javascript), you must provide your own additional lists.
For macros created with `widget`, you can extract them from the story, like so, to
generate a `my_widgets.json` file:

```sh
./scripts/check_sugarcube_macros.py -p my_story.html --extract_widgets -o my_widgets.json
```

For macros created with `Macro.add`, you have to manually create that list, refer to
the [Checks section](#checks) and the `sugarcube_macro_list.json` file to see how to
create that file (it's pretty simple). If you still have macros that cannot be made
known to the checker, the `--ignore_unknown` option can be used to ignore those errors.

### Extracting Sugarcube passages

If you have a Sugarcube story in the form of the final html file (or the intermediate
"project" html file used by Twine), and you wish to extract passages into individual
twee files (`.tw`/`.twee`), then you can use the extraction scripts. To extract an
individual passage into a `.tw` file, use this:

```sh
./scripts/extract_passage.py -i my_story.html -p "My Passage" -o my_passage.tw
```

Where `My Passage` is the name of the passage you want to extract and `my_passage.tw`
is the output file.

To extract all passages, which is faster if you intend to do that anyway, then you
can use the following:

```sh
./scripts/extract_story.py -i my_story.html -o some/path/to/my_story
```

This will create one file for each passage of the story and place them in the
`some/path/to/my_story` directory. By default, the file names are the names of
the passage converted to `snake_case`, e.g., "My Passage" ends up in `my_passage.tw`.
To change this behavior, you can use the `--filename_case` option and pass either
`snake_case`, `CamelCase`, or `identity` to it, where "identity" preserves the
passage name exactly (e.g., `My Passage.tw`).

The scripts could also be used manually to create a story out of the `.tw` files,
but at that point, you'd be better off using the Bazel system described below.

## Getting started

Familiarity with Bazel is preferable, but the following guide should be sufficient
to get started, even without being familiar with it.

### Requirements

 - Bazel: [See Bazel's Getting Started Guide](https://bazel.build/start)
 - Python3 environment (3.8+): The scripts are written in Python. Only a vanilla
   Python interpreter is needed, no pip/uv packages required or virtual environments.

### Importing sugarcube_bazel into a Bazel project

A Bazel project starts off as a `MODULE.bazel` file in the top-level directory of
the project. When using `sugarcube_bazel`, it should, at minimum, contain the following:

```py
# In MODULE.bazel:
module(name = "my_game_project")

git_repository = use_repo_rule("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

bazel_dep(name = "bazel_skylib", version = "1.9.0")
bazel_dep(name = "rules_python", version = "2.0.2")

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

The lines with `bazel_skylib` and `rules_python` simply import dependencies
of `sugarcube_bazel`. And, of course, the `git_repository` statement imports `sugarcube_bazel`
itself. Note that the `branch = "main"` line should be replaced by either `commit = "<commit hash>"`
or `tag = "<tag name>"` to point to a particular commit or tag rather than the latest state
of the main branch (which is unstable and not consistently reproducible).

### Defining a sugarcube_story target

The following section describes how to define a sugarcube story and the libraries of passages
it depends on. For a complete example, see the `examples/the_mall` directory.

Bazel, like most build systems, works by defining build "targets", usually on a per-directory
basis. In Bazel, any file called `BUILD.bazel` in a directory is interpreted as defining such
targets, and the directories are searched down recursively, stopping at any directory that
does not contain a `BUILD.bazel` (so, you might have to leave empty `BUILD.bazel` files in
intermediate directories that don't contain targets). Typically, at the top-level, you
would create a `sugarcube_story` target which is going to be the top-level target to
build your SugarCube game. This is how a top-level `BUILD.bazel` file might look like:

```py
# In BUILD.bazel:
load('@sugarcube_bazel//:defs.bzl', 'sugarcube_story')

package(default_visibility = ["//:__subpackages__"])

filegroup(
  name = "user_scripts",
  srcs = ["user_script.js"],
)

filegroup(
  name = "user_stylesheet",
  srcs = ["user_stylesheet.css"],
)

filegroup(
  name = "user_macros",
  srcs = ["user_macros.json"],
)

sugarcube_story(
  name = "my_story",
  title = "My Story Title",
  ifid = "<insert IFID number>",
  extra_html = [":user_scripts", ":user_stylesheet"],
  user_macros = [":user_macros"],
  deps = [
    "//passages:start",
    "//passages/my_story", # Game-specific libraries
  ],
)
```

The `sugarcube_story` rule expects a few parameters:

 - `name`: The name of the target, which can be anything, it will not appear in the
   output but it's how you refer to that target within Bazel.
 - `title`: The title of the story as it will appear in places such as the title-bar
   of the browser's tab.
 - `ifid`: The IFID (Interactive Fiction IDentifier) number assigned to this SugarCube
   game. See [TADS.org](https://www.tads.org/ifidgen/ifidgen).
 - `deps`: The list of libraries of passages that the story depends on. See the next
   section on definining libraries.
 - `extra_html` (optional): Extra html or html-adjacent files to insert next to
   passage data elements in the final output. This can contain `.html` files (will be
   copy-pasted directly into output), `.css` files (will be wrapped in a `<style>` block),
   and `.js` files (will be wrapped in a `<script>` block). Note that there can be multiple files.
   This is where you would typically add what Twine calls user scripts or stylesheets.
   Note that scripts and stylesheets can also just be inside 'twee' files.
 - `user_macros` (optional): The user macros list. This is a special json file that is used to list
   all the macros that are added in the user scripts. This is needed because this build
   system checks passages for correct usage of macros (e.g., correct nesting, no deprecated
   macros, etc.). So, it needs to know all the macros that exist. The built-in macros of
   Sugarcube are already known (see `scripts/sugarcube_macro_list.json`). The macros
   created via "widget" passages (i.e., with the "widget" macro) will be automatically
   gathered during the build. What cannot be gathered automatically, however, are
   the macros that are added via Javascript, e.g., using `Macro.add()`, either in one
   of the user scripts html elements or wherever else they could be added. And, thus,
   this `user_macros` option is where you provide a list of such macros, see the list
   of built-in macros (`scripts/sugarcube_macro_list.json`) to see how that json file
   looks like.
 - `format` (optional): The Sugarcube format file to use, by default it uses
   `@sugarcube_bazel//formats/sugarcube-2.37.3:format`, but other formats are
   available and new or custom ones can be passed in.

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
words, the build directory should contain all the files needed to deploy/serve the game.

### Defining sugarcube_library targets

To create libraries of passages, you use the `sugarcube_library` rule, which takes
the following arguments:

 - `name`: The name of the target (how other libraries or story targets refer to it).
 - `srcs`: The set of source files, aka passages, for this library. Passages are just
   plain text files. They can be 'twee' files with the extensions `.tw` or `.twee`
   defining one or more passages (see [Twee docs](https://twinery.org/cookbook/terms/terms_twee.html)).
 - `tags` (optional): The set of tags to apply to all the passages in this library,
   see sugarcube docs for the usage of tags. Most importantly, **the `widget` tag has
   to be present on libraries that contain widgets** (i.e., widget passages must be
   segregated from other passages and marked as such).
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
    "media_coding.tw", # List of passages
    "link_coding.tw",
    "stats_coding.tw",
  ],
)

# Define a new sugarcube library for game locations menu.
sugarcube_library(
  name = "locations",
  srcs = [
    "locations.tw", # A passage listing links to locations to visit.
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
    "start.tw",          # The special 'Start' passage.
    "stats.tw",          # A passage for displaying character stats.
    "story_author.tw",   # The story author display passage.
    "story_caption.tw",  # The story caption display passage.
    "story_init.tw",     # The special 'StoryInit' passage that initializes all variables.
    "story_menu.tw",     # The story side-bar menu passage.
    "story_subtitle.tw", # The story sub-title passage.
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

A typical 'twee' passage might look like this:

```
:: Stats
[img[passages/mall_pic.jpg]]

<<if $mallvisits is 0>>
You have not yet visited the mall, what are you waiting for?
<<elseif $mallvisits lt 5>>
You've been to the mall, did you find anything interesting?
<<else>>
You're insane! You keep going to the mall expecting a different outcome!
<</if>>

<<return>>
```

That's pretty much all there is to it. There are probably some Bazel-specific knowledge missing
or assumed from this quick guide, see the Bazel docs for more info.

### Checks

This sugarcube build system provides several layers of checks.

First, inherent to Bazel, all files declared as making up a target of any kind,
including `filegroup` targets (e.g., typical for assets like images and videos),
must exist. Any modification to the files triggers the re-building of whatever
steps are necessary (i.e., that's why build systems exist, ultimately). Similarly,
required fields cannot be missing from target definitions.

Second, certain rules are applied to make sure that only libraries are listed
as dependencies and only ordinary files are listed as data dependencies (aka assets).
That prevents basic mix-ups in defining the targets.

Third, passage names (aka IDs) are gathered for all the passages that ultimately
form one complete story, and any duplicate names will result in a build error
pointing to the location of the duplication.

Finally, each passage's content is checked for proper use of Sugarcube Macros.
The checks include:

 - Wrong nesting of "container" macros, e.g., `<<foo ..>>` without a `<</foo>>`
   to close it out at that right nesting level.
 - Deprecated macros, e.g., `<<remember ..>>` should be replaced with `<<set ..>>`.
 - Unknown macros or widgets, catching typos.
 - Macros defined with `<<widget ..>>` that have the same name or the name of
   a built-in macro (or a Javascript `Macro.add`). This is not technically
   an error when rendering the sugarcube story, but it's a very bad thing to
   do because which macro takes precedence is arbitrary (depends on load order).

This final set of checks can be disabled with a build command option, e.g.:

```sh
bazel build //:my_story --@sugarcube_bazel//:enable_checks=false
```

The macro usage checks rely on having a full list of macros available. That
list is constructed from the built-in macros (see `scripts/sugarcube_macro_list.json`),
then adding the story's `user_macros` (see `sugarcube_story` rule described
above), and finally gathering all the macros defined using `<<widget ..>>` in
the passages marked with the `widget` tag (as required by Sugarcube). Thus,
any macro that your story uses that is neither part of the core Sugarcube
language nor defined in a widget passage should be listed in a json file
and passed in via the `user_macros` argument to your `sugarcube_story`.
This exert from the built-in list should give a good idea of how that
json file looks like:

```json
{
  "if": {
    "tags": ["elseif", "else"],
    "is_container": true
  },
  "capture": {
    "is_container": true
  },
  "set": {},
  "remember": {
    "deprecated_for": "set"
  }
}
```

A simple macro with no "content" (no open and close pair) just needs to be
listed (like `"set": {},`). A container macro should have the boolean
`is_container` field (like `"capture": { "is_container": true }`). A multi-stage
macro, such as `if-elseif-else`, should list its intermediate tags.
Finally, a deprecated macro can point to its suggested replacement, if no
direct replacement exists, use `"deprecated_for": "unknown"`.

### Converting an existing Sugarcube story

If you have an existing Sugarcube story that you wish to convert or port over to
using `sugarcube_bazel`, there are a few options to make this easier.

In the `scripts` directory, there are two useful scripts: `extract_passage` and
`extract_story`. The first can be used to find a particular passage, by name,
within a (compiled) Sugarcube story (aka, the main html file) and extract it into
a plain text `.tw` file as used by `sugarcube_bazel`. That can be useful when
manually porting over a project, and going about it passage by passage. For example:

```sh
bazel build //scripts:extract_passage
bazel-bin/scripts/extract_passage --input the_mall.html --passage StoryCaption --output story_caption.tw
```

The `extract_story` script is a more comprehensive conversion script that attempts
to extract all passages and extra html elements (like scripts and stylesheets), and
ultimately produce a directory containing all of those broken up into individual
files. Obviously, this could lead to numerous files and a very messy result, given
that Sugarcube stories have no internal structure, just a flat set of passages and
other html elements. For example, for a story in `the_mall.html`,
you could output all passages, user-scripts, and stylesheets, along with a (hopefully)
working `BUILD.bazel` file into a destination directory `the_mall_dir` using
the following command (also, telling it that assets are located in the `images`
subdirectory):

```sh
bazel build //scripts:extract_story
bazel-bin/scripts/extract_story --input the_mall.html --output the_mall_dir/ --build_file --assets_dir images
```

Of course, once this `sugarcube_bazel` version has been produced, it is still going
to need a lot of work to organize the passages in meaningful ways to get any real
benefit from using this build system. Regardless, these scripts are provided to
make that process easier.

## License

BSD 2-Clause License

Copyright (c) 2026, SomebodyElse

## Disclaimer

This is provided 'as is', do not expect any level of maintenance or response to
issues or pull requests. This is mainly released because I made this and found it
very useful (and miles better than anything else that I know of to create SugarCube or
Twine games, like twine, tweego, etc.), and I just wanted to share it.

