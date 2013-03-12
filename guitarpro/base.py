# This file is part of alphaTab.
#
#  alphaTab is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  alphaTab is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with alphaTab.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import division

import math
import struct
import copy

class GuitarProException(Exception):
    pass

class GPFileBase(object):
    DEFAULT_CHARSET = "UTF-8"
    BEND_POSITION = 60
    BEND_SEMITONE = 25

    _supportedVersions = []
    version = None
    
    def __init__(self, data=None):
        self.data = data

    def close(self):
        self.data.close()
    
    def initVersions(self, supportedVersions):
        self._supportedVersions = supportedVersions
    
    # Reading
    # =======
    def skip(self, count):
        self.data.read(count)

    def readByte(self):
        result = struct.unpack('B', self.data.read(1))
        return result[0]

    def readSignedByte(self):
        result = struct.unpack('b', self.data.read(1))
        return result[0]

    def readBool(self):
        result = struct.unpack('?', self.data.read(1))
        return result[0]
    
    def readShort(self): 
        result = struct.unpack('<h', self.data.read(2))
        return result[0]
    
    def readInt(self): 
        result = struct.unpack('<i', self.data.read(4))
        return result[0]

    def readFloat(self):
        result = struct.unpack('<f', self.data.read(4))
        return result[0]
    
    def readDouble(self):
        result = struct.unpack('<d', self.data.read(8))
        return result[0]

    def readString(self, size, length=-2):
        if length == -2:
            length = size
        count = size if size > 0 else length
        s = self.data.read(count)
        return s[:(length if length >= 0 else size)]

    def readByteSizeString(self, size):
        return self.readString(size, self.readByte())

    def readIntSizeCheckByteString(self):
        d = self.readInt() - 1
        return self.readByteSizeString(d)
    
    def readByteSizeCheckByteString(self):
        return self.readByteSizeString(self.readByte() - 1)

    def readIntSizeString(self):
        return self.readString(self.readInt())
    
    def readVersion(self):
        if self.version is None:
            self.version = self.readByteSizeString(30)
        return self.version in self._supportedVersions
    
    def toChannelShort(self, data):
        value = max(-32768, min(32767, (data << 3) - 1))
        return max(value, -1) + 1

    # Writing
    # =======
    def placeholder(self, count):
        self.data.write('\x00' * count)

    def writeByte(self, data):
        packed = struct.pack('B', data)
        self.data.write(packed)

    def writeSignedByte(self, data):
        packed = struct.pack('b', data)
        self.data.write(packed)

    def writeBool(self, data):
        packed = struct.pack('?', data)
        self.data.write(packed)
    
    def writeShort(self, data):
        packed = struct.pack('<h', data)
        self.data.write(packed)
    
    def writeInt(self, data):
        packed = struct.pack('<i', data)
        self.data.write(packed)

    def writeFloat(self, data):
        packed = struct.pack('<f', data)
        self.data.write(packed)
    
    def writeDouble(self, data):
        packed = struct.pack('<d', data)
        self.data.write(packed)

    def writeString(self, data, size=None):
        if size is None:
            size = len(data)
        self.data.write(data)
        placeholder = '\x00' * (size - len(data))
        self.data.write(placeholder)

    # def writeString(self, data, size, length=-2):
    #     if length == -2:
    #         length = size
    #     count = size if size > 0 else length
    #     s = self.data.read(count)
    #     return s[:(length if length >= 0 else size)]

    def writeByteSizeString(self, data, size=None):
        if size is None:
            size = len(data)
        self.writeByte(len(data))
        return self.writeString(data, size)

    def writeIntSizeCheckByteString(self, data):
        # self.writeInt(len(data) - 1)
        self.writeInt(len(data) + 1)
        return self.writeByteSizeString(data)
    
    def writeByteSizeCheckByteString(self, data):
        # self.writeByte() - 1
        self.writeByte(len(data) + 1)
        return self.writeByteSizeString(data)

    def writeIntSizeString(self, data):
        self.writeInt(len(data))
        return self.writeString(data)
    
    def writeVersion(self, index=None):
        if self.version is not None:
            self.writeByteSizeString(self.version, 30)
        else:
            self.writeByteSizeString(self._supportedVersions[index], 30)

    def fromChannelShort(self, data):
        value = max(-128, min(127, (data >> 3) - 1))
        return value + 1

    # Misc
    # ====
    def getTiedNoteValue(self, stringIndex, track):
        measureCount = track.measureCount()
        if measureCount > 0:
            for m2 in range(measureCount):
                m = measureCount - 1 - m2
                measure = track.measures[m]
                for b2 in range(measure.beatCount()):
                    b = measure.beatCount() - 1 - b2
                    beat = measure.beats[b]   
                    for voice in beat.voices:
                        if not voice.isEmpty:
                            for note in voice.notes:
                                if note.string == stringIndex:
                                    return note.value
        return -1


class RepeatGroup(object):
    '''This class can store the information about a group of measures which are repeated
    '''
    def __init__(self):
        self.measureHeaders = []
        self.closings = []
        self.openings = []
        self.isClosed = False
    
    def addMeasureHeader(self, h):
        if not len(self.openings):
            self.openings.append(h)
        
        self.measureHeaders.append(h)
        h.repeatGroup = self
        
        if h.repeatClose > 0:
            self.closings.append(h)
            self.isClosed = True
        # a new item after the header was closed? -> repeat alternative reopens the group
        elif self.isClosed:
            self.isClosed = False
            self.openings.append(h)


class Song(object):
    '''This is the toplevel node of the song model. 

    It contains basic information about the stored song. 
    '''
    def __init__(self):
        '''Initializes a new instance of the Song class. 
        '''
        self.measureHeaders = []
        self.tracks = []
        self.title = ""
        self.subtitle = ""
        self.artist = ""
        self.album = ""
        self.words = ""
        self.music = ""
        self.copyright = ""
        self.tab = ""
        self.instructions = ""
        self.notice = ""
        self._currentRepeatGroup = RepeatGroup()
    
    def addMeasureHeader(self, header):
        '''Adds a new measure header to the song. 
        :param: header the measure header to add. 
        '''
        header.song = self
        self.measureHeaders.append(header)
        
        # if the group is closed only the next upcoming header can
        # reopen the group in case of a repeat alternative, so we 
        # remove the current group 
        if header.isRepeatOpen or (self._currentRepeatGroup.isClosed and header.repeatAlternative <= 0):
            self._currentRepeatGroup = RepeatGroup()
            
        self._currentRepeatGroup.addMeasureHeader(header)
    
    def addTrack(self, track):
        '''Adds a new track to the song. 
        :param: track the track to add. 
        '''
        track.song = self
        self.tracks.append(track)

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return (self.title == other.title and
            self.subtitle == other.subtitle and
            self.artist == other.artist and
            self.album == other.album and
            self.words == other.words and
            self.music == other.music and
            self.copyright == other.copyright and
            self.tab == other.tab and
            self.instructions == other.instructions and
            self.notice == other.notice and
            self.lyrics == other.lyrics and
            self.pageSetup == other.pageSetup and
            self.tempoName == other.tempoName and
            self.tempo == other.tempo and
            self.hideTempo == other.hideTempo and
            self.key == other.key and
            self.octave == other.octave and
            # self.measureHeaders == other.measureHeaders and
            self.tracks == other.tracks)


class LyricLine(object):
    '''A lyrics line. 
    '''
    def __init__(self, startingMeasure, lyrics):
        self.startingMeasure = startingMeasure
        self.lyrics = lyrics

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.startingMeasure == other.startingMeasure and
            self.lyrics == other.lyrics)

class Lyrics(object):
    '''Represents a collection of lyrics lines for a track. 
    '''
    MAX_LINE_COUNT = 5

    def __init__(self, trackChoice=0):
        self.trackChoice = trackChoice
        self.lines = []
    
    def lyricsBeats(self):
        full = ''
        for line in self.lines:
            if line is not None:
                full += line.lyrics + '\n'
        ret = full.trim()
        ret = ret.replace('\n', ' ')
        ret = ret.replace('\r', ' ')
        return ret.split(' ')

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.trackChoice == other.trackChoice and
            self.lines == other.lines)

class Point(object):
    '''A point construct using floating point coordinates.
    '''
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.x == other.x and
            self.y == other.y)


class Padding(object):
    '''A padding construct. 
    '''
    def __init__(self, right, top, left, bottom):
        self.right = right
        self.top = top
        self.left = left
        self.bottom = bottom
    
    def getHorizontal(self):
        return self.left + self.right
        
    def getVertical(self):
        return self.top + self.bottom

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.right == other.right and
            self.top == other.top and
            self.left == other.left and
            self.bottom == other.bottom)


class HeaderFooterElements(object):
    '''A list of the elements which can be shown in the header and footer 
    of a rendered song sheet. All values can be combined using bit-operators as they are flags. 
    '''
    NONE = 0x0
    TITLE = 0x1
    SUBTITLE = 0x2
    ARTIST = 0x4
    ALBUM = 0x8
    WORDS = 0x10
    MUSIC = 0x20
    WORDS_AND_MUSIC = 0x40
    COPYRIGHT = 0x80
    PAGE_NUMBER = 0x100
    ALL = (NONE | TITLE | SUBTITLE | ARTIST | ALBUM | WORDS | MUSIC |
        WORDS_AND_MUSIC | COPYRIGHT | PAGE_NUMBER)


class PageSetup(object):
    '''The page setup describes how the document is rendered. 
    It contains page size, margins, paddings, and how the title elements are rendered. 
    
    Following template vars are available for defining the page texts:
       %TITLE% - Will get replaced with Song.title
       %SUBTITLE% - Will get replaced with Song.subtitle
       %ARTIST% - Will get replaced with Song.artist
       %ALBUM% - Will get replaced with Song.album
       %WORDS% - Will get replaced with Song.words
       %MUSIC% - Will get replaced with Song.music
       %WORDSANDMUSIC% - Will get replaced with the according word and music values
       %COPYRIGHT% - Will get replaced with Song.copyright
       %N% - Will get replaced with the current page number (if supported by layout)
       %P% - Will get replaced with the number of pages (if supported by layout)
    '''
    def __init__(self):
        self.pageSize = Point(210,297)
        self.pageMargin = Padding(10,15,10,10)
        self.scoreSizeProportion = 1
        self.headerAndFooter = HeaderFooterElements.ALL
        self.title = "%TITLE%"
        self.subtitle = "%SUBTITLE%"
        self.artist = "%ARTIST%"
        self.album = "%ALBUM%"
        self.words = "Words by %WORDS%"
        self.music = "Music by %MUSIC%"
        self.wordsAndMusic = "Words & Music by %WORDSMUSIC%"
        self.copyright = ("Copyright %COPYRIGHT%\n"
                          "All Rights Reserved - International Copyright Secured")
        self.pageNumber = "Page %N%/%P%"

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.pageSize == other.pageSize and
            self.pageMargin == other.pageMargin and
            self.scoreSizeProportion == other.scoreSizeProportion and
            self.headerAndFooter == other.headerAndFooter and
            self.title == other.title and
            self.subtitle == other.subtitle and
            self.artist == other.artist and
            self.album == other.album and
            self.words == other.words and
            self.music == other.music and
            self.wordsAndMusic == other.wordsAndMusic and
            self.copyright == other.copyright and
            self.pageNumber == other.pageNumber)


class Tempo(object):
    '''A song tempo in BPM. 
    '''
    def inUsq(self): 
        return self.tempoToUsq(value)
    
    def __init__(self):
        self.value = 120
    
    # def copy(self, tempo):
    #     self.value = tempo.value
    
    def tempoToUsq(self, tempo):
        # BPM to microseconds per quarternote
        return int(60000000 / tempo)

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return self.value == other.value


class MidiChannel(object):
    '''A midi channel describes playing data for a track
    '''
    DEFAULT_PERCUSSION_CHANNEL = 9
    DEFAULT_INSTRUMENT = 24
    DEFAULT_VOLUME = 104
    DEFAULT_BALANCE = 64
    DEFAULT_CHORUS = 0
    DEFAULT_REVERB = 0
    DEFAULT_PHASER = 0
    DEFAULT_TREMOLO = 0
    
    def __init__(self):
        self.channel = 0
        self.effectChannel = 0
        self.instrument(self.DEFAULT_INSTRUMENT)
        self.volume = self.DEFAULT_VOLUME
        self.balance = self.DEFAULT_BALANCE
        self.chorus = self.DEFAULT_CHORUS
        self.reverb = self.DEFAULT_REVERB
        self.phaser = self.DEFAULT_PHASER
        self.tremolo = self.DEFAULT_TREMOLO
    
    def instrument(self, newInstrument=-1):
        if newInstrument != -1:
            self._instrument = newInstrument
        return self._instrument
    
    def isPercussionChannel(self):
        return self.channel == self.DEFAULT_PERCUSSION_CHANNEL

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.channel == other.channel and
            self.effectChannel == other.effectChannel and
            self.volume == other.volume and
            self.balance == other.balance and
            self.chorus == other.chorus and
            self.reverb == other.reverb and
            self.phaser == other.phaser and
            self.tremolo == other.tremolo and
            self.instrument() == other.instrument())


class MeasureHeader(object):
    '''A measure header contains metadata for measures over multiple tracks. 
    '''
    DEFAULT_KEY_SIGNATURE = 0
    
    def hasMarker(self):
        return self.marker is not None
    
    def length(self):
        return self.timeSignature.numerator * self.timeSignature.denominator.time()
    
    def __init__(self):
        self.number = 0
        self.start = Duration.QUARTER_TIME
        self.timeSignature = TimeSignature()
        self.keySignature = self.DEFAULT_KEY_SIGNATURE
        self.keySignatureType = 0
        self.tempo = Tempo()
        self.marker = None
        self.tripletFeel = TripletFeel.None_
        self.isRepeatOpen = False
        self.repeatClose = -1
        self.repeatAlternative = 0
        self.realStart = -1

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.number == other.number and
            self.hasDoubleBar == other.hasDoubleBar and
            self.keySignature == other.keySignature and
            self.keySignatureType == other.keySignatureType and
            self.start == other.start and
            self.realStart == other.realStart and
            self.timeSignature == other.timeSignature and
            self.tempo == other.tempo and
            self.marker == other.marker and
            self.isRepeatOpen == other.isRepeatOpen and
            self.repeatAlternative == other.repeatAlternative and
            self.repeatClose == other.repeatClose and
            # self.repeatGroup == other.repeatGroup and
            self.tripletFeel == other.tripletFeel)


class Color(object):
    '''A RGB Color.
    '''
    def __init__(self, r, g, b, a):
        self.r = r
        self.g = g
        self.b = b
        self.a = a
    
    def asRgbString(self):
        if self.a == 1:
            return "rgb(%d,%d,%d)" % (r, g, b)
        else:
            return "rgba(%d,%d,%d,%d)" % (r, g, b, a)
    
    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return (self.r == other.r and
            self.g == other.g and
            self.b == other.b and
            self.a == other.a)

    @staticmethod
    def fromRgb(r, g, b):
        return Color(r, g, b, 1)
    
    @staticmethod
    def fromARgb(r, g, b, a):
        return Color(r, g, b, a)

Color.Black = Color.fromRgb(0, 0, 0)
Color.Red = Color.fromRgb(255, 0, 0)


class Marker(object):
    '''A marker annotation for beats
    '''
    DEFAULT_COLOR = Color.Red
    DEFAULT_TITLE = "Untitled"
    
    def __init__(self):
        self.title = ''
        self.color = None
        self.measureHeader = None

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return (self.title == other.title and
            self.color == other.color)


class Track(object):
    '''A track contains multiple measures
    '''
    def stringCount(self):
        return len(self.strings)
    
    def measureCount(self):
        return len(self.measures)
    
    def __init__(self):
        self.number = 0
        self.offset = 0
        self.isSolo = False
        self.isMute = False
        self.name = ""
        self.measures = []
        self.strings = []
        self.channel = MidiChannel()
        self.color = Color.fromRgb(255, 0, 0)
    
    def addMeasure(self, measure):
        measure.track = self
        self.measures.append(measure)

    def __str__(self):
        return '<guitarpro.base.Track %d>' % (self.number)

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.fretCount == other.fretCount and
            self.number == other.number and
            self.offset == other.offset and
            self.isSolo == other.isSolo and
            self.isMute == other.isMute and
            self.isPercussionTrack == other.isPercussionTrack and
            self.is12StringedGuitarTrack == other.is12StringedGuitarTrack and
            self.isBanjoTrack == other.isBanjoTrack and
            self.name == other.name and
            self.measures == other.measures and
            self.strings == other.strings and
            self.port == other.port and
            self.channel == other.channel and
            self.color == other.color)


class GuitarString(object):
    '''A guitar string with a special tuning.
    '''
    def __init__(self):
        self.number = 0
        self.value = 0

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.number == other.number and
            self.value == other.value)
    
    # def clone(self):
    #     pass


class Tuplet(object):
    '''Represents a n:m tuplet
    '''
    
    def __init__(self):
        self.enters = 1
        self.times = 1
    
    def convertTime(self, time):
        return int(time * self.times / self.enters);
    
    def __eq__(self, other):
        return (self.enters == other.enters and 
            self.times == other.times)
        
    # def clone(self, factory):
    #     pass

Tuplet.NORMAL = Tuplet()


class Duration(object):
    '''A duration.
    '''
    QUARTER_TIME = 960
    
    WHOLE = 1
    HALF = 2
    QUARTER = 4
    EIGHTH = 8
    SIXTEENTH = 16
    THIRTY_SECOND = 32
    SIXTY_FOURTH = 64
    
    # The time resulting with a 64th note and a 3/2 tuplet
    MIN_TIME = int(int(QUARTER_TIME * (4.0 / SIXTY_FOURTH)) * 2 / 3)
    
    def time(self):
        result = int(self.QUARTER_TIME * (4.0 / self.value))
        if self.isDotted:
            result += int(result / 2)
        elif self.isDoubleDotted:
            result += int((result / 4) * 3)
        return self.tuplet.convertTime(result)
    
    def index():
        index = 0
        value = self.value
        # while (value = (value >> 1)) > 0:
        #     index += 1
        while True:
            value = (value >> 1)
            if value > 0:
                index += 1
            else:
                break
        return index
    
    def __init__(self):
        self.value = self.QUARTER
        self.isDotted = False
        self.isDoubleDotted = False
        self.tuplet = Tuplet()
    
    @staticmethod
    def fromTime(time, minimum, diff):
        # duration = minimum.clone(factory)
        duration = copy.deecopy(minimum)
        tmp = Duration()
        tmp.value = WHOLE
        tmp.isDotted = True
        while True:
            tmpTime = tmp.time()
            if tmpTime - diff <= time:
                if abs(tmpTime - time) < abs(duration.time() - time):
                    # duration = tmp.clone(factory)
                    duration = copy.deepcopy(tmp)
            if tmp.isDotted:
                tmp.isDotted = False
            elif tmp.tuplet == Tuplet.NORMAL:
                tmp.tuplet.enters = 3
                tmp.tuplet.times = 2
            else:
                tmp.value = tmp.value * 2
                tmp.isDotted = True
                tmp.tuplet.enters = 1
                tmp.tuplet.times = 1
            if tmp.value > self.SIXTY_FOURTH:
                break
        return duration
    
    # def clone(self, factory):
    #     pass
    
    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return (other.value == self.value and
            other.isDotted == self.isDotted and
            other.isDoubleDotted == self.isDoubleDotted and
            # other.tuplet.equals(tuplet);
            other.tuplet == self.tuplet)


class MeasureClef(object):
    '''A list of available clefs
    '''
    Treble = 0
    Bass = 1
    Tenor = 2
    Alto = 3


class Measure(object):
    '''A measure contains multiple beats
    '''
    DEFAULT_CLEF = MeasureClef.Treble

    def beatCount(self):
        return len(self.beats)
    
    def end(self):
        return self.start() + self.length()
    
    def number(self):
        return self.header.number
    
    def keySignature(self):
        return self.header.keySignature
    
    def repeatClose(self):
        return self.header.repeatClose
    
    def start(self):
        return self.header.start
    
    def length(self):
        return self.header.length()
    
    def tempo(self):
        return self.header.tempo
    
    def timeSignature(self):
        return self.header.timeSignature

    def isRepeatOpen(self):
        return self.header.isRepeatOpen
    
    def tripletFeel(self):
        return self.header.tripletFeel
    
    def hasMarker(self):
        return self.header.hasMarker()
    
    def marker(self):
        return self.header.marker
    
    def __init__(self, header):
        self.header = header
        self.clef = self.DEFAULT_CLEF
        self.beats = []
    
    def addBeat(self, beat):
        beat.measure = self
        beat.index = len(self.beats)
        self.beats.append(beat)

    def __str__(self):
        measure = self.number()
        track = self.track.number
        return '<guitarpro.base.Measure %d on Track %d>' % (measure, track)

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return (self.clef == other.clef and
            self.beats == other.beats and
            self.header == other.header)


class VoiceDirection(object):
    '''Voice directions indicating the direction of beams. 
    '''
    None_ = 0
    Up = 1
    Down = 2


class Voice(object):
    '''A voice contains multiple notes.
    '''
    def isRestVoice(self):
        return len(self.notes) == 0
    
    def __init__(self, index):
        self.duration = Duration()
        self.notes = []
        self.index = index
        self.direction = VoiceDirection.None_
        self.isEmpty = True
    
    def addNote(self, note):
        note.voice = self
        self.notes.append(note)
        self.isEmpty = False

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.duration == other.duration and
            self.notes == other.notes and
            self.index == other.index and
            self.direction == other.direction and
            self.isEmpty == other.isEmpty)


class BeatStrokeDirection(object):
    '''All beat stroke directions
    '''
    None_ = 0
    Up = 1
    Down = 2


class BeatStroke(object):
    '''A stroke effect for beats. 
    '''
    def __init__(self):
        self.direction = BeatStrokeDirection.None_
    
    def getIncrementTime(self, beat):
        duration = 0
        if self.value > 0:
            for voice in beat.voices:
                if voice.isEmpty:
                    continue
                currentDuration = voice.duration.time()
                if duration == 0 or currentDuration < duration:
                    duration = (currentDuration if currentDuration <= Duration.QUARTER_TIME 
                        else Duration.QUARTER_TIME)
            if duration > 0:
                return round((duration / 8.0) * (4.0 / value))
        return 0

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return self.direction == other.direction


class BeatEffect(object):
    '''This class contains all beat effects.
    '''
    hasRasgueado = False
    pickStroke = 0
    hasPickStroke = False
    chord = None
    vibrato = False
    tremoloBar = None
    mixTableChange = None

    def isChord(self):
        return self.chord is not None

    def isTremoloBar(self):
        return self.tremoloBar is not None

    def __init__(self):
        self.tapping = False
        self.slapping = False
        self.popping = False
        self.fadeIn = False
        self.stroke = BeatStroke()

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return (self.stroke == other.stroke and
            self.hasRasgueado == other.hasRasgueado and
            self.pickStroke == other.pickStroke and
            self.hasPickStroke == other.hasPickStroke and
            self.chord == other.chord and
            self.fadeIn == other.fadeIn and
            self.vibrato == other.vibrato and
            self.tremoloBar == other.tremoloBar and
            self.mixTableChange == other.mixTableChange and
            self.tapping == other.tapping and
            self.slapping == other.slapping and
            self.popping == other.popping)


class Beat(object):
    '''A beat contains multiple voices. 
    '''
    MAX_VOICES = 2
    
    def isRestBeat(self):
        for voice in self.voices:
            if not voice.isEmpty and not voice.isRestVoice():
                return False
        return True
    
    def getRealStart(self):
        offset = self.start - self.measure.start()
        return self.measure.header.realStart + offset
    
    def setText(self, text):
        text.beat = self
        self.text = text

    def setChord(self, chord):
        chord.beat = self
        self.effect.chord = chord
    
    def ensureVoices(self, count):
        while len(self.voices) < count: # as long we have not enough voice
            # create new ones
            voice = Voice(len(self.voices))
            voice.beat = self
            self.voices.append(voice)
    
    def getNotes(self):
        notes = []
        for voice in self.voices:
            for note in voice.notes:
                notes.append(note)
        return notes
    
    def __init__(self):
        self.start = Duration.QUARTER_TIME
        self.effect = BeatEffect()
        self.text = None
        self.voices = []
        for i in range(Beat.MAX_VOICES):
            voice = Voice(i)
            voice.beat = self
            self.voices.append(voice)

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.voices == other.voices and
            self.text == other.text and
            self.start == other.start and
            self.effect == other.effect and
            self.index == other.index)


class HarmonicEffect(object):
    '''A harmonic note effect
    '''
    # Lists all harmonic type groups
    # [i][0] -> The note played
    # [i][1] -> The according harmonic note to [i][0]
    NATURAL_FREQUENCIES = [[12, 12], [9, 28], [5, 28], [7, 19], [4, 28], [3, 31]]
          
    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.type == other.type and
            self.data == other.data)


class GraceEffectTransition(object):
    '''All transition types for grace notes. 
    '''
    # No transition
    None_ = 0
    # Slide from the grace note to the real one
    Slide = 1
    # Perform a bend from the grace note to the real one
    Bend = 2
    # Perform a hammer on 
    Hammer = 3


class GraceEffect(object):
    '''A grace note effect.
    '''  
    def durationTime(self):
        '''Gets the duration of the effect. 
        '''
        return int((Duration.QUARTER_TIME / 16.00) * self.duration)
    
    def __init__(self, ):
        '''Initializes a new instance of the GraceEffect class. 
        '''
        self.fret = 0
        self.duration = 1
        self.velocity = Velocities.DEFAULT
        self.transition = GraceEffectTransition.None_
        self.isOnBeat = False
        self.isDead = False

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.isDead == other.isDead and
            self.duration == other.duration and
            self.velocity == other.velocity and
            self.fret == other.fret and
            self.isOnBeat == other.isOnBeat and
            self.transition == other.transition)

    # def clone(self, factory):
    #     pass


class TrillEffect(object):
    '''A trill effect. 
    '''  
    def __init__(self):
        self.fret = 0
        self.duration = Duration()
    
    # def clone(self):
    #     pass

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.fret == other.fret and
            self.duration == other.duration)


class TremoloPickingEffect(object):
    '''A tremolo picking effect. 
    '''
    def __init__(self):
        '''Initializes a new instance of he TremoloPickingEffect class.
        :param: factory the factory to create new instances. 
        '''
        self.duration = Duration()
    
    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return self.duration == other.duration

    # def clone(self):
    #     pass


class NoteEffect(object):
    '''Contains all effects which can be applied to one note. 
    '''
    def __init__(self):
        self.bend = None
        self.harmonic = None
        self.grace = None
        self.trill = None
        self.tremoloPicking = None
        self.vibrato = False
        self.deadNote = False
        self.slide = False
        self.hammer = False
        self.ghostNote = False
        self.accentuatedNote = False
        self.heavyAccentuatedNote = False
        self.palmMute = False
        self.staccato = False
        self.letRing = False
        self.isFingering = False
        self.leftHandFinger = -1
        self.rightHandFinger = -1
        self.slideType = -1
    
    def isBend(self):
        return self.bend is not None and len(self.bend.points)
        
    def isHarmonic(self):
        return self.harmonic is not None
    
    def isGrace(self):
        return self.grace is not None
    
    def isTrill(self):
        return self.trill is not None
    
    def isTremoloPicking(self):
        return self.tremoloPicking is not None
    
    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.leftHandFinger == other.leftHandFinger and
            self.rightHandFinger == other.rightHandFinger and
            self.isFingering == other.isFingering and
            self.bend == other.bend and
            self.harmonic == other.harmonic and
            self.grace == other.grace and
            self.trill == other.trill and
            self.tremoloPicking == other.tremoloPicking and
            self.vibrato == other.vibrato and
            self.deadNote == other.deadNote and
            self.slideType == other.slideType and
            self.slide == other.slide and
            self.hammer == other.hammer and
            self.ghostNote == other.ghostNote and
            self.accentuatedNote == other.accentuatedNote and
            self.heavyAccentuatedNote == other.heavyAccentuatedNote and
            self.palmMute == other.palmMute and
            self.staccato == other.staccato and
            self.letRing == other.letRing)

    # def clone(self, factory):
    #     pass


class Note(object):
    '''Describes a single note. 
    '''
    def realValue(self):
        if self._realValue == -1:
            self._realValue = self.value + self.voice.beat.measure.track.strings[self.string - 1].value
        return self._realValue
    
    def __init__(self):
        self._realValue = -1
        self.value = 0
        self.velocity = Velocities.DEFAULT
        self.string = 1
        self.isTiedNote = False
        self.swapAccidentals = False
        self.effect = NoteEffect()
        # self.duration = 0
        # self.tuplet = 0
        # self.durationPercent = 1

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (
            # self.duration == other.duration and
            # self.tuplet == other.tuplet and
            self.value == other.value and
            self.velocity == other.velocity and
            self.string == other.string and
            self.isTiedNote == other.isTiedNote and
            self.effect == other.effect and
            # self.durationPercent == other.durationPercent and
            self.swapAccidentals == other.swapAccidentals)


class Chord(object):
    '''A chord annotation for beats
    '''
    def stringCount(self):
        return len(self.strings)
    
    def noteCount(self):
        count = 0
        for string in self.strings:
            if string >= 0:
                count += 1
        return count
    
    def __init__(self, length):
        self.strings = [-1] * length

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return (self.firstFret == other.firstFret and
            self.strings == other.strings and
            self.name == other.name)


class BeatText(object):
    '''A text annotation for beats.
    '''
    def __init__(self):
        self.value = ''
        self.beat = None

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return self.value == other.value


class MixTableItem(object):
    '''A mixtablechange describes several track changes. 
    '''
    def __init__(self):
        self.value = 0
        self.duration = 0
        self.allTracks = False

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.value == other.value and
            self.duration == other.duration and
            self.allTracks == other.allTracks)

class MixTableChange(object):
    '''A mixtablechange describes several track changes. 
    '''
    def __init__(self):
        self.volume = MixTableItem()
        self.balance = MixTableItem()
        self.chorus = MixTableItem()
        self.reverb = MixTableItem()
        self.phaser = MixTableItem()
        self.tremolo = MixTableItem()
        self.instrument = MixTableItem()
        self.tempo = MixTableItem()
        self.hideTempo = True

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return None
        return (self.volume == other.volume and
            self.balance == other.balance and
            self.chorus == other.chorus and
            self.reverb == other.reverb and
            self.phaser == other.phaser and
            self.tremolo == other.tremolo and
            self.instrument == other.instrument and
            self.tempoName == other.tempoName and
            self.tempo == other.tempo and
            self.hideTempo == other.hideTempo)


class BendTypes(object):
    '''All Bend presets
    '''
    ## Bends 
    # No Preset
    None_ = 0
    # A simple bend
    Bend = 1
    # A bend and release afterwards
    BendRelease = 2
    # A bend, then release and rebend
    BendReleaseBend = 3
    # Prebend
    Prebend = 4
    # Prebend and then release
    PrebendRelease = 5
    
    ## Tremolobar    
    # Dip the bar down and then back up
    Dip = 6
    # Dive the bar
    Dive = 7
    # Release the bar up
    ReleaseUp = 8
    # Dip the bar up and then back down
    InvertedDip = 9
    # Return the bar
    Return = 10
    # Release the bar down
    ReleaseDown = 11


class BendPoint(object):
    '''A single point within the BendEffect or TremoloBarEffect 
    '''
    def __init__(self, position, value, vibrato):
        '''Initializes a new instance of the BendPoint class. 
        '''
        self.position = position
        self.value = value
        self.vibrato = vibrato
    
    def getTime(self, duration):
        '''Gets the exact time when the point need to be played (midi)
        :param: duration the full duration of the effect
        :param: the time when this point is processed according to the given song duration
        '''
        return int(duration * self.position / BendEffect.MAX_POSITION)

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return (self.position == other.position and
            self.value == other.value and
            self.vibrato == other.vibrato)


class BendEffect(object):
    '''This effect is used for creating string bendings and whammybar effects (tremolo bar)
    '''
    # The note offset per bend point offset. 
    SEMITONE_LENGTH = 1
    # The max position of the bend points (x axis)
    MAX_POSITION = 12
    # The max value of the bend points (y axis)
    MAX_VALUE = SEMITONE_LENGTH * 12

    def __init__(self):
        '''Initializes a new instance of the BendEffect
        '''
        self.type = BendTypes.None_
        self.value = 0
        self.points = []
    
    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return (self.type == other.type and
            self.value == other.value and
            self.points == other.points)

    # def clone(self, factory):
    #     pass


class TripletFeel(object):
    '''A list of different triplet feels
    '''
    None_ = 0
    Eighth = 1
    Sixteenth = 2


class TimeSignature(object):
    '''A time signature.
    '''
    def __init__(self):
        self.numerator = 4
        self.denominator = Duration()

    def __eq__(self, other):
        if other is None or not isinstance(other, self.__class__):
            return False
        return (self.numerator == other.numerator and
            self.denominator == other.denominator)


class Velocities(object):
    '''A list of velocities / dynamics
    '''
    MIN_VELOCITY = 15
    VELOCITY_INCREMENT = 16
    PIANO_PIANISSIMO = MIN_VELOCITY
    PIANISSIMO = MIN_VELOCITY + VELOCITY_INCREMENT
    PIANO = MIN_VELOCITY + (VELOCITY_INCREMENT * 2)
    MEZZO_PIANO = MIN_VELOCITY + (VELOCITY_INCREMENT * 3)
    MEZZO_FORTE = MIN_VELOCITY + (VELOCITY_INCREMENT * 4)
    FORTE = MIN_VELOCITY + (VELOCITY_INCREMENT * 5)
    FORTISSIMO = MIN_VELOCITY + (VELOCITY_INCREMENT * 6)
    FORTE_FORTISSIMO = MIN_VELOCITY + (VELOCITY_INCREMENT * 7)
    DEFAULT = FORTE