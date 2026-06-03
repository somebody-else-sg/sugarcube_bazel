load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")

SugarcubeLibraryInfo = provider(
    "Info specific to a sugarcube library of passages.",
    fields = ["passages", "widgets"]
)

def _sugarcube_library_impl(ctx):
    srcs = ctx.files.srcs
    inputs = depset(srcs)
    output_file = ctx.actions.declare_file(ctx.label.name + ".html")

    args = ctx.actions.args()
    args.add(output_file)
    args.add_joined(ctx.attr.tags, join_with = " ", omit_if_empty=False)
    args.add_all(srcs)

    ctx.actions.run(
        mnemonic = "ScpToHtml",
        executable = ctx.executable._scp_to_html,
        arguments = [args],
        inputs = inputs,
        outputs = [output_file],
    )

    runfiles = ctx.runfiles(files = ctx.files.data)
    all_libs = []
    all_runfiles = []
    transitive_passages = []
    transitive_widgets = []
    for dep in ctx.attr.deps:
        all_libs = all_libs + [depset([lib_file]) for lib_file in dep[DefaultInfo].files.to_list()]
        all_runfiles.append(dep[DefaultInfo].default_runfiles)
        if not SugarcubeLibraryInfo in dep:
            fail("Should only have sugarcube libraries in dependencies!", "Are you sure this is not data?", "Target", dep.label, "as dependency of", ctx.label)
        transitive_passages.append(dep[SugarcubeLibraryInfo].passages)
        transitive_widgets.append(dep[SugarcubeLibraryInfo].widgets)
    for dep in ctx.attr.data:
        if SugarcubeLibraryInfo in dep:
            fail("Should not have sugarcube library in a data dependency!", "Are you sure this is data?", "Data target", dep.label, "as dependency of", ctx.label)
    runfiles = runfiles.merge_all(all_runfiles)
    if "widget" in ctx.attr.tags:
        passages = depset([], transitive = transitive_passages)
        widgets = depset(srcs, transitive = transitive_widgets)
    else:
        passages = depset(srcs, transitive = transitive_passages)
        widgets = depset([], transitive = transitive_widgets)

    return [DefaultInfo(files = depset([output_file], transitive = all_libs), default_runfiles = runfiles), SugarcubeLibraryInfo(passages = passages, widgets = widgets)]

sugarcube_library = rule(
    implementation = _sugarcube_library_impl,
    attrs = {
        "srcs": attr.label_list(allow_files = [".scp"]),
        "deps": attr.label_list(allow_files = [".html"], providers = [SugarcubeLibraryInfo]),
        "data": attr.label_list(),
        "_scp_to_html": attr.label(
            default = Label("@sugarcube_bazel//scripts:scp_to_html"),
            executable = True,
            cfg = "exec",
        ),
    },
)

def _html_escape(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')

def _sugarcube_story_impl(ctx):
    runfiles = ctx.runfiles()
    all_libs = []
    all_runfiles = []
    all_passages = []
    all_widgets = []
    for dep in ctx.attr.deps:
        all_libs = all_libs + dep[DefaultInfo].files.to_list()
        all_runfiles.append(dep[DefaultInfo].default_runfiles)
        if not SugarcubeLibraryInfo in dep:
            fail("Should only have sugarcube libraries in dependencies!", "Are you sure this is not data?", "Target", dep.label, "as dependency of", ctx.label)
        all_passages += dep[SugarcubeLibraryInfo].passages.to_list()
        all_widgets += dep[SugarcubeLibraryInfo].widgets.to_list()
    all_inputs = depset(all_libs)
    runfiles = runfiles.merge_all(all_runfiles)

    all_assets = []
    for rf in runfiles.files.to_list():
        asset_path = ctx.actions.declare_file(paths.join(ctx.label.name, rf.path))
        ctx.actions.symlink(output=asset_path, target_file=rf)
        all_assets.append(asset_path)

    if ctx.attr._enable_checks_flag[BuildSettingInfo].value:
        builtin_macros = ctx.attr._builtin_macros.files.to_list()
        for mac in ctx.attr.user_macros:
            builtin_macros += mac.files.to_list()

        widgets_macros = ctx.actions.declare_file(ctx.label.name + "_widgets_macros.json")
        widgets_args = ctx.actions.args()
        widgets_args.add_all("--macros", builtin_macros)
        widgets_args.add_all("--passages", all_widgets)
        widgets_args.add("--output", widgets_macros)
        widgets_args.add("--extract_widgets")
        widgets_args.add("--ignore_unknown")
        ctx.actions.run(
            mnemonic = "CollectWidgetMacros",
            executable = ctx.executable._check_sugarcube_macros,
            arguments = [widgets_args],
            inputs = depset(builtin_macros + all_widgets),
            outputs = [widgets_macros],
        )

        macro_errors = ctx.actions.declare_file(ctx.label.name + "_macro_errors.json")
        check_args = ctx.actions.args()
        check_args.add_all("--macros", builtin_macros + [widgets_macros])
        check_args.add_all("--passages", all_passages + all_widgets)
        check_args.add("--output", macro_errors)
        ctx.actions.run(
            mnemonic = "CheckMacroUsage",
            executable = ctx.executable._check_sugarcube_macros,
            arguments = [check_args],
            inputs = depset(builtin_macros + [widgets_macros] + all_passages + all_widgets),
            outputs = [macro_errors],
        )


    inner_file = ctx.actions.declare_file(ctx.label.name + "_inner.html")
    inner_args = ctx.actions.args()
    inner_args.add_all(all_inputs)
    inner_args.add(inner_file)
    ctx.actions.run(
        mnemonic = "MakeInnerData",
        executable = ctx.executable._make_inner_data,
        arguments = [inner_args],
        inputs = all_inputs,
        outputs = [inner_file],
    )

    for fmt_file in ctx.attr.format.files.to_list():
        if fmt_file.path.endswith("fmt_name"):
            fmt_name_file = fmt_file
        if fmt_file.path.endswith("fmt_version"):
            fmt_version_file = fmt_file
        if fmt_file.path.endswith("fmt_template"):
            fmt_template_file = fmt_file

    html_inserts = []
    for sheet in ctx.attr.user_stylesheet:
        html_inserts += sheet.files.to_list()
    for script in ctx.attr.user_script:
        html_inserts += script.files.to_list()

    storydata_file = ctx.actions.declare_file(ctx.label.name + "_storydata.html")
    storydata_cmd = "cat <(echo -n '<tw-storydata name=\"{}\" startnode=\"1\" ifid=\"{}\" format=\"') {} <(echo -n '\" format-version=\"') {} <(echo '\" hidden>') {} <(echo '</tw-storydata>') > {}".format(
        _html_escape(ctx.attr.title), _html_escape(ctx.attr.ifid),
        fmt_name_file.path, fmt_version_file.path,
        " ".join([f.path for f in html_inserts + [inner_file]]), storydata_file.path)
    ctx.actions.run_shell(
        mnemonic = "MakeStoryData",
        inputs = [inner_file] + [fmt_name_file, fmt_version_file] + html_inserts,
        outputs = [storydata_file],
        command = storydata_cmd,
    )

    output_file = ctx.actions.declare_file(paths.join(ctx.label.name, "index.html"))
    args = ctx.actions.args()
    args.add(_html_escape(ctx.attr.title))
    args.add(storydata_file)
    args.add(fmt_template_file)
    args.add(output_file)
    make_story_inputs = [storydata_file, fmt_template_file]
    if ctx.attr._enable_checks_flag[BuildSettingInfo].value:
        make_story_inputs += [macro_errors]
    ctx.actions.run(
        mnemonic = "MakeStory",
        executable = ctx.executable._make_story,
        arguments = [args],
        inputs = make_story_inputs,
        outputs = [output_file],
    )

    return [
        DefaultInfo(files = depset([output_file]), runfiles = ctx.runfiles(files = all_assets)),
        OutputGroupInfo(assets = all_assets, macro_errors = depset([macro_errors] if ctx.attr._enable_checks_flag[BuildSettingInfo].value else [])),
    ]

sugarcube_story = rule(
    implementation = _sugarcube_story_impl,
    attrs = {
        "title": attr.string(mandatory = True),
        "ifid": attr.string(mandatory = True),
        "deps": attr.label_list(),
        "user_stylesheet": attr.label_list(),
        "user_script": attr.label_list(),
        "user_macros": attr.label_list(),
        "format": attr.label(
            default = Label("@sugarcube_bazel//formats/sugarcube-2.37.3:format"),
            cfg = "exec",
        ),
        "_make_story": attr.label(
            default = Label("@sugarcube_bazel//scripts:make_story"),
            executable = True,
            cfg = "exec",
        ),
        "_make_inner_data": attr.label(
            default = Label("@sugarcube_bazel//scripts:make_inner_data"),
            executable = True,
            cfg = "exec",
        ),
        "_check_sugarcube_macros": attr.label(
            default = Label("@sugarcube_bazel//scripts:check_sugarcube_macros"),
            executable = True,
            cfg = "exec",
        ),
        "_builtin_macros": attr.label(
            default = Label("@sugarcube_bazel//scripts:builtin_macros"),
            cfg = "exec",
        ),
        "_enable_checks_flag": attr.label(
            default = Label("@sugarcube_bazel//:enable_checks"),
            cfg = "exec",
        ),
    },
)


def _sugarcube_format_impl(ctx):
    fmt_name_file = ctx.actions.declare_file(ctx.label.name + "_fmt_name")
    fmt_version_file = ctx.actions.declare_file(ctx.label.name + "_fmt_version")
    fmt_template_file = ctx.actions.declare_file(ctx.label.name + "_fmt_template")
    fmt_args = ctx.actions.args()
    fmt_args.add(ctx.attr.src.files.to_list()[0])
    fmt_args.add(fmt_name_file)
    fmt_args.add(fmt_version_file)
    fmt_args.add(fmt_template_file)
    ctx.actions.run(
        mnemonic = "SplitFormatFile",
        executable = ctx.executable._split_format_file,
        arguments = [fmt_args],
        inputs = ctx.attr.src.files.to_list(),
        outputs = [fmt_name_file, fmt_version_file, fmt_template_file],
    )

    return [
        DefaultInfo(files = depset([fmt_name_file, fmt_version_file, fmt_template_file])),
    ]

sugarcube_format = rule(
    implementation = _sugarcube_format_impl,
    attrs = {
        "src": attr.label(mandatory = True, allow_single_file = True,),
        "_split_format_file": attr.label(
            default = Label("@sugarcube_bazel//scripts:split_format_file"),
            executable = True,
            cfg = "exec",
        ),
    },
)



