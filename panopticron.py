#! /usr/bin/python

from __future__ import division

import sys, os.path
import gobject
import pygst
pygst.require("0.10")
import gst
from optparse import OptionParser
import tempfile

def duration(filepath):
    """Given a filepath, return the length (in nanoseconds) of the media"""
    assert os.path.isfile(filepath), "File %s doesn't exist" % filepath
    gobject.threads_init()
    d = gst.parse_launch("filesrc name=source ! decodebin2 ! fakesink")
    source = d.get_by_name("source")
    source.set_property("location", filepath)
    d.set_state(gst.STATE_PLAYING)
    d.get_state()
    format = gst.Format(gst.FORMAT_TIME)
    duration = d.query_duration(format)[0]
    d.set_state(gst.STATE_NULL)
    return duration

def width_height(filepath):
    assert os.path.isfile(filepath)
    gobject.threads_init()
    pipeline = gst.parse_launch("filesrc name=source ! decodebin2 name=decoder ! fakesink")
    source = pipeline.get_by_name("source")
    source.set_property("location", filepath)
    pipeline.set_state(gst.STATE_PLAYING)
    pipeline.get_state()
    pad = list(pipeline.get_by_name("decoder").src_pads())[1]
    caps = pad.get_caps()[0]
    width, height =  caps['width'], caps['height']
    pipeline.set_state(gst.STATE_NULL)
    return width, height

def file_source(filename, start, duration, (row, col), (width, height)):
    bin = gst.Bin()

    fileuri = "file://" + os.path.abspath(filename)
    gsrc = gst.element_factory_make("gnlfilesource")
    gsrc.props.location       = fileuri
    gsrc.props.start          = 0
    gsrc.props.duration       = duration
    gsrc.props.media_start    = start
    gsrc.props.media_duration = duration

    bin.add(gsrc)

    queue = gst.element_factory_make("queue")
    bin.add(queue)
    def on_pad(comp, pad, elements):
        convpad = elements.get_compatible_pad(pad, pad.get_caps())
        pad.link(convpad)
    gsrc.connect("pad-added", on_pad, queue)


    scale = gst.element_factory_make("videoscale")
    bin.add(scale)
    queue.link(scale)

    filter = gst.element_factory_make("capsfilter")
    bin.add(filter)
    filter.set_property("caps", gst.Caps("video/x-raw-yuv, width=%d, height=%d" % (width, height)))
    scale.link(filter)

    videobox = gst.element_factory_make("videobox")
    bin.add(videobox)
    videobox.props.top = -(col * height)
    videobox.props.left = -(row * width)
    videobox.set_property("border-alpha", 0)
    filter.link(videobox)

    bin.add_pad(gst.GhostPad("src", videobox.get_pad("src")))

    return bin

def one_iteration(intermediate_filename, source_filename, source_duration, (source_width, source_height), (rows, cols), (row, col)):
    print "Doing (%d, %s)" % (row, col)
    pipeline = gst.Pipeline()

    if intermediate_filename is not None:
        filesource = gst.element_factory_make("filesource")
        pipeline.add(filesource)
        filesource.set_property("location", intermediate_filename)

        y4mdec = gst.element_factory_make("y4mdec")
        pipeline.add(y4mdec)
        filesource.link(y4mdec)

    window_duration = source_duration / (rows * cols)
    start = long(col * window_duration  + row *(window_duration * cols))
    window_width, window_height = int(source_width / rows), int(source_width / cols)

    this_window = file_source(source_filename, start, window_duration, (row, col), (window_width, window_height))
    pipeline.add(this_window)

    if intermediate_filename is not None:
        mix = gst.element_factory_make("videomixer")
        pipeline.add(mix)

        this_window.link(mix)
        filesource.link(mix)

    _, new_intermediate_file = tempfile.mkstemp(prefix="panopticron.", suffix=".y4m")
    print new_intermediate_file

    y4menc = gst.element_factory_make("y4menc")
    pipeline.add(y4menc)
    if intermediate_filename is None:
        this_window.link(y4menc)
    else:
        mix.link(y4menc)

    progressreport = gst.element_factory_make("progressreport")
    pipeline.add(progressreport)
    y4menc.link(progressreport)


    sink = gst.element_factory_make("filesink")
    sink.props.location = new_intermediate_file
    pipeline.add(sink)
    progressreport.link(sink)

    play_pipeline(pipeline)


def main(args):
    parser = OptionParser()
    parser.add_option("-o", '--output', dest="output_filename", default="output.ogv")
    parser.add_option("-s", "--size", dest="size", default=4)

    options, source = parser.parse_args()
    source = os.path.abspath(source[0])

    source_width, source_height = width_height(source)

    rows, cols = int(options.size), int(options.size)

    source_duration = duration(source)
    num_windows = rows * cols
    window_duration = source_duration / num_windows

    window_width, window_height = int(source_width / rows), int(source_width / cols)

    print "The source is %d sec long, there will be %s windows, each will show %d sec" % (source_duration/gst.SECOND, num_windows, window_duration/gst.SECOND)
    one_iteration(None, source, source_duration, (source_width, source_height), (rows, cols), (0, 0))


def play_pipeline(pipeline):
    loop = gobject.MainLoop(is_running=True)
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    def on_message(bus, message, loop):
        if message.type == gst.MESSAGE_EOS:
            loop.quit()
        elif message.type == gst.MESSAGE_ERROR:
            print message
            loop.quit()
    bus.connect("message", on_message, loop)
    pipeline.set_state(gst.STATE_PLAYING)
    loop.run()
    pipeline.set_state(gst.STATE_NULL)

if __name__ == '__main__':
    main(sys.argv[1:])
