#!/usr/bin/python3

import math
import struct
import sys

def make_code_table (code_size):
    codes = []
    for i in range (2 ** (code_size - 1)):
        codes.append ((i,))
    clear_code = 2 ** (code_size - 1)
    eoi_code = clear_code + 1
    codes.append (clear_code)
    codes.append (eoi_code)
    return (codes, clear_code, eoi_code)

def decode_lzw (data, start_code_size):
    full_code_size = start_code_size
    values = []
    code = 0
    code_size = 0
    (codes, clear_code, eoi_code) = make_code_table (start_code_size)
    last_code = clear_code
    for d in data:
        n_available = 8
        while n_available > 0:
            # Number of bits to get
            n_bits = min (full_code_size - code_size, n_available)

            # Extract bits from octet
            new_bits = d & ((1 << n_bits) - 1)
            d >>= n_bits
            n_available -= n_bits

            # Add new bits to the top of the code
            code = new_bits << code_size | code
            code_size += n_bits

            # Keep going until we get a full code word
            if code_size < full_code_size:
                continue

            if code == eoi_code:
                return values
            elif code == clear_code:
                (codes, clear_code, eoi_code) = make_code_table (start_code_size)
                full_code_size = start_code_size
                last_code = clear_code
            elif code < len (codes):
                for v in codes[code]:
                    values.append (v)
                # Bug in gdk-pixbuf is assuming clear code is at start?
                # Bug in gdk-pixbuf is stopping adding codes after 4095?
                if last_code != clear_code and len (codes) < 4095:
                    codes.append (codes[last_code] + (codes[code][0],))
                last_code = code
            elif code == len (codes):
                codes.append (codes[last_code] + (codes[last_code][0],))
                for v in codes[-1]:
                    values.append (v)
                last_code = code
            else:
                print ('Ignoring unexpected code %d' % code)
            full_code_size = math.ceil (math.log2 (len (codes) + 1))
            code = 0
            code_size = 0

    print ('LZW without end code')
    return values

def get_disposal_method_string (disposal_method):
    if disposal_method == 0:
        return 'none'
    elif disposal_method == 1:
        return 'keep'
    elif disposal_method == 2:
        return 'restore background'
    elif disposal_method == 3:
        return 'restore previous'
    else:
        return str (disposal_method)

def decode_extension (label, blocks):
    if label == 0xf9:
        if len (blocks) != 1:
            print ('Multiple blocks in Graphic Control Extension')
            return False
        if len (blocks[0]) != 4:
            print ('Length mismatch in Graphic Control Extension')
            return False
        (flags, delay_time, transparent_color) = struct.unpack ('<BHB', blocks[0])
        disposal_method = flags >> 2 & 0x7
        user_input = flags & 0x02 != 0
        has_transparent = flags & 0x01 != 0
        print ('Graphic Control Extension:')
        print ('  Delay Time: %d/100 ms' % delay_time)
        if has_transparent:
            print ('  Transparent Color: %d' % transparent_color)
        elif transparent_color != 0:
            print ('  Transparent Color: %d (!)' % transparent_color)
        print ('  Disposal Method: %s' % get_disposal_method_string (disposal_method))
        print ('  User Input: %s' % repr (user_input))
    elif label == 0xfe:
        comment = ''
        for block in blocks:
            comment += str (block.decode ('utf-8'))
        print ('Comment Extension:')
        print ('  Comment: %s' % repr (comment))
    elif label == 0xff:
        if len (blocks) < 1:
            print ('Not enough blocks in Application Extension')
            return False
        if len (blocks[0]) != 11:
            print ('Application Extension invalid block size')
            return False
        try:
            identifier = str (blocks[0][:8], 'ascii')
        except:
            print ('Application Extension invalid identifier')
            return False
        try:
            authentication_code = str (blocks[0][8:], 'ascii')
        except:
            print ('Application Extension invalid authentication code')
            return False
        if identifier == 'NETSCAPE':
            print ('NETSCAPE Extension:')
            print ('  Version: %s' % authentication_code)
            for block in blocks[1:]:
                if block[0] == 0x01:
                    if len (block) != 3:
                        print ('NETSCAPE loop sub-block invalid length')
                        return False
                    (loop_count,) = struct.unpack ('<xH', block)
                    print ('  Loop Count: %d' % loop_count)
                else:
                    print ('  Sub-Block %d: %s' % (block[0], repr (block[1:])))
        else:
            print ('Application Extension:')
            print ('  Application Identifier: %s' % identifier)
            print ('  Application Authentication Code: %s' % authentication_code)
            for block in blocks[1:]:
                print ('  Data: %s' % repr (block))
    else:
        print ('Extension: 0x%02x' % label)
        for block in blocks:
            print ('  Data: %s' % repr (block))
    return True

def decode_gif (f):
    data = open (f, 'rb').read ()

    if len (data) < 6 or data[:3] != b'GIF':
        print ('Not a GIF file')
        return False

    version = data[3:6]
    if not version in [b'87a', b'89a']:
        print ('Unknown GIF version %s' % version)
        return False

    if len (data) < 13:
        print ('Not enough space for GIF header')
        return False

    header = data[:13]
    (_, width, height, flags, background_color, pixel_aspect_ratio) = struct.unpack ('<6sHHBBB', header)
    has_color_table = flags & 0x80 != 0
    depth = ((flags >> 4) & 0x7) + 1
    color_table_sorted = flags & 0x08 != 0
    color_table_size = flags & 0x7
    print ('Size: %dx%d' % (width, height))
    print ('Original Depth: %d' % depth)
    print ('Background Color: %d' % background_color)
    print ('Pixel Aspect Ratio: %d' % pixel_aspect_ratio)

    payload = data[13:]

    global_colors = []
    if has_color_table:
        n_colors = 2 ** (color_table_size + 1)
        if len (payload) < n_colors * 3:
            print ('Not enough space for color table')
            return False
        color_map = payload[:n_colors * 3]
        payload = payload[len (color_map):]
        for i in range (n_colors):
            offset = i * 3
            (red, green, blue) = struct.unpack ('BBB', color_map[offset: offset + 3])
            global_colors.append ('#%02x%02x%02x' % (red, green, blue))
        print ('Colors (%d): %s' % (len (global_colors), ', '.join (global_colors)))
    else:
        if color_table_size != 0:
            print ('Color Table Size: %s' % color_table_size)
    if color_table_sorted:
        print ('Color Table Sorted: %s' % str (color_table_sorted))

    while len (payload) > 0:
        if payload[0] == 0x2c:
            if len (payload) < 10:
                print ('No enough space for image descriptor')
                return False
            descriptor = payload[:10]
            payload = payload[10:]
            (left, top, width, height, flags) = struct.unpack ('<xHHHHB', descriptor)
            has_color_table = flags & 0x80 != 0
            interlace = flags & 0x40 != 0
            color_table_sorted = flags & 0x20 != 0
            color_table_size = flags & 0x7
            print ('Image:')
            print ('  Position: %dx%d' % (left, top))
            print ('  Size: %dx%d' % (width, height))
            print ('  Interlace: %s' % str (interlace))
            local_colors = []
            if has_color_table:
                n_colors = 2 ** (color_table_size + 1)
                if len (payload) < n_colors * 3:
                    print ('Not enough space for color table')
                    return False
                color_map = payload[:n_colors * 3]
                payload = payload[len (color_map):]
                for i in range (n_colors):
                    offset = i * 3
                    (red, green, blue) = struct.unpack ('BBB', color_map[offset: offset + 3])
                    local_colors.append ('#%02x%02x%02x' % (red, green, blue))
                print ('Colors (%d): %s' % (len (local_colors), ', '.join (local_colors)))
            else:
                if color_table_size != 0:
                    print ('  Color Table Size: %s' % color_table_size)
            if color_table_sorted:
                print ('  Color Table Sorted: %s' % str (color_table_sorted))
            if len (payload) < 1:
                print ('Not enough space for image data')
                return False
            (lzw_code_size, ) = struct.unpack ('B', payload[:1])
            payload = payload[1:]
            codes = b''
            while True:
                if len (payload) < 1:
                    print ('Out of data reading image data')
                    return False
                (block_size, ) = struct.unpack ('B', payload[:1])
                payload = payload[1:]
                if block_size == 0:
                    break
                if len (payload) < block_size:
                    print ('Out of data reading image data')
                    return False
                block = payload[:block_size]
                colors = global_colors
                if len (local_colors) > 0:
                    colors = local_colors
                codes += block
                payload = payload[block_size:]
            values = decode_lzw (codes, lzw_code_size + 1)
            print ('  Data (%d): %s' % (len (values), values))
        elif payload[0] == 0x21:
            payload = payload[1:]
            if len (payload) < 1:
                print ('Not enough space for extension header')
                return False
            label = payload[0]
            payload = payload[1:]
            blocks = []
            while True:
                if len (payload) < 1:
                    print ('Not enough space for extention data')
                    return
                (block_size, ) = struct.unpack ('B', payload[:1])
                payload = payload[1:]
                if block_size == 0:
                    break
                if len (payload) < block_size:
                    print ('Out of data reading extension data')
                    return False
                blocks.append (payload[:block_size])
                payload = payload[block_size:]
            if not decode_extension (label, blocks):
                return False
        elif payload[0] == 0x3b:
            payload = payload[1:]
            if len (payload) > 0:
                print ('Extra Data: %s' % repr (payload))
            return True
        else:
            print ('Unknown block')
            print (payload)
            return False

    print ('No trailer')
    return False

if len (sys.argv) < 2:
    exit ()

decode_gif (sys.argv[1])
