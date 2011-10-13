#! /usr/bin/python

from __future__ import division

import sys, os.path
import gobject
import pygst
pygst.require("0.10")
import gst
from optparse import OptionParser

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

def music_stream(music_filename, music_start, all_video_files, transition_length):
    music_start = float(music_start)
    music_start = long(music_start * gst.SECOND)
        
    assert os.path.isfile(music_filename)
    file_lengths = sum(duration(x) for x in all_video_files) - transition_length * (len(all_video_files) - 1)

    music_src = gst.element_factory_make("gnlfilesource")
    music_src.props.location = "file://"+os.path.abspath(music_filename)
    music_src.props.start          = 0
    music_src.props.duration       = file_lengths
    music_src.props.media_start    = music_start
    music_src.props.media_duration = file_lengths
    music_src.props.priority       = 1
    acomp = gst.element_factory_make("gnlcomposition")
    acomp.add(music_src)
    return acomp

def file_source(filename, start, duration, position, window_sizes):
    bin = gst.Bin()

    fileuri = "file://" + os.path.abspath(filename)
    gsrc = gst.element_factory_make("gnlfilesource")
    gsrc.props.location       = fileuri
    gsrc.props.start          = start
    gsrc.props.duration       = duration
    gsrc.props.media_start    = 0
    gsrc.props.media_duration = duration

    row, col = position
    width, height = window_sizes


    compo = gst.element_factory_make("gnlcomposition")
    compo.add(gsrc)
    bin.add(compo)

    queue = gst.element_factory_make("queue")
    bin.add(queue)
    def on_pad(comp, pad, elements):
        convpad = elements.get_compatible_pad(pad, pad.get_caps())
        pad.link(convpad)
    compo.connect("pad-added", on_pad, queue)


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
    print "\t", videobox.props.top, videobox.props.left
    filter.link(videobox)

    bin.add_pad(gst.GhostPad("src", videobox.get_pad("src")))

    return bin


def main():
    source = "source.mov"

    output_width, output_height = 640, 480

    source_width, source_height = width_height(source)

    rows, cols = 6, 6

    source_duration = duration(source)
    num_windows = rows * cols
    window_duration = source_duration / num_windows

    window_width, window_height = output_width / rows, output_width / cols

    pipeline = gst.Pipeline()
    mix = gst.element_factory_make("videomixer")
    pipeline.add(mix)

    print "The source is %d sec long, there will be %s windows, each will show %d sec" % (source_duration/gst.SECOND, num_windows, window_duration/gst.SECOND)
    for row, col in [(row, col) for row in range(rows) for col in range(cols)]:
        start = long(col * window_duration  + row *(window_duration * cols))
        print row, col

        window_source = file_source(source, start, window_duration, (row, col), (window_width, window_height))
        pipeline.add(window_source)
        window_source.link(mix)

    ffmpeg = gst.element_factory_make("ffmpegcolorspace")
    pipeline.add(ffmpeg)
    mix.link(ffmpeg)

    prog = gst.element_factory_make("progressreport")
    pipeline.add(prog)
    ffmpeg.link(prog)

    venc = gst.element_factory_make("theoraenc")
    pipeline.add(venc)
    prog.link(venc)

    mux = gst.element_factory_make("oggmux")
    pipeline.add(mux)
    venc.link(mux)

    sink = gst.element_factory_make("filesink")
    sink.props.location = "output.ogv"
    pipeline.add(sink)
    mux.link(sink)

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
    main()