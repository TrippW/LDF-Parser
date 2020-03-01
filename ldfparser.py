"""This file is intended to parse an LDF into its components"""
import os
import re

def trim(data):
    """removes spaces from a list"""
    for i in range(len(data)):
        data[i] = data[i].replace(' ', '')
    return data

class LDFParser:
    """parses LDF files into usable data"""
    def __init__(self, starting_file=None):
        """Set up all needed parameters"""
        self.loaded = False
        self.parsed = False
        self.frames = {}
        self.nodes = {}
        self.signals = {}
        self.attributes = {}
        self.all_text = None
        self.current_file = starting_file
        if starting_file:
            self.set_file(starting_file)


    def _reset_data(self):
        """When setting a new file, clear all data"""
        self.loaded = False
        self.parsed = False
        self.frames = {}
        self.nodes = {}
        self.signals = {}
        self.attributes = {}

    def set_file(self, file_name):
        """takes a path to an ldf file, then reads and parses it"""
        if str(file_name[-3:]).lower() == 'ldf':
            if os.path.exists(file_name):
                self.current_file = file_name
                self._reset_data()
                self._read_file()
            else:
                raise FileNotFoundError(file_name+" doesn't exist")
        else:
            raise ValueError('Incorrect file type')

    def _read_file(self):
        """reads the text from the ldf file"""
        self.loaded = False
        with open(self.current_file) as file:
            self.all_text = file.read()
        self.loaded = True
        self._parse_file()

    def _parse_file(self):
        """parses the text from the ldf into nodes, signals, frames, and attributes"""
        self._parse_nodes(*self._find_ends('Nodes'))
        self._parse_all_frames(*self._find_ends('Frames'))
        self._parse_all_signals(*self._find_ends('Signals'))
        self._parse_all_attributes(*self._find_ends('Node_attributes'))
        self.parsed = True
        del self.all_text

    def _find_ends(self, term, text=None):
        """utility function to find the brackets for a term in text"""
        if not text:
            text = self.all_text
        #add len of term since we know what we asked for and add 2 for
        #the space and brace
        start = text.find(term+' {')+len(term)+2
        if start == len(term) + 1:
            start = text.find(term+'{')+len(term)+1
        if start == len(term):
            raise Exception("Term not found")
        end = temp = start
        while ('{' in text[temp:end]) or (end == temp):
            temp = end+1
            end = text.find('}', temp)
            if(end == -1) or (end == len(text)):
                break
        return (start, end)

    def _parse_nodes(self, start, end):
        """parses the nodes into master and slaves"""
        master_start = self.all_text.find("Master: ", start, end)+len("Master: ")
        master_end = self.all_text.find(",", master_start, end)
        master = self.all_text[master_start: master_end]
        slave_start = self.all_text.find("Slaves: ", start, end)+len("Slaves: ")
        slave_end = self.all_text.find(";", slave_start, end)
        slaves = self.all_text[slave_start: slave_end].split(",")
        #remove spaces from slave names
        slaves = trim(slaves)
        self.nodes['master'] = master
        self.nodes['slaves'] = slaves

    def _parse_all_signals(self, start, end):
        """initiates the parsing of all signals and their encoding"""
        signals = self.all_text[start:end].replace('\n', '')\
                  .replace(' ', '').split(';')
        signals = trim(signals)
        for signal in signals:
            if signal:
                self._parse_signal(signal)
        self._match_encoding()

    def _match_encoding(self):
        """matches encoding to the appropriate signal"""
        #find the signal to encoding match
        el_start, el_end = self._find_ends('Signal_representation')
        encoding_link_list = self.all_text[el_start:el_end]\
                             .replace(' ', '').replace('\n', '').split(';')
        encoding_link = {}
        for element in encoding_link_list:
            if element.strip():
                data = element.split(':')
                encoding_link[data[0]] = data[1]

        #find the encoding and add it to each signal
        ed_start, ed_end = self._find_ends('Signal_encoding_types')
        encoding_data_text = self.all_text[ed_start:ed_end].replace('\n', '')
        ed_end -= ed_start
        ed_start = 0

        #so long as there are encodings left, we look through them
        while ed_start not in (ed_end, -1):
            name = encoding_data_text[ed_start:encoding_data_text.find('{', ed_start)]
            name = name.strip().replace(' ', '')
            #make sure the name isn't empty so we don't try to find an empty string
            if name:
                ed_start, _end = self._find_ends(name, encoding_data_text)
                #if we have a match between encoding and a signal, we can add the encoding
                if name in encoding_link.keys():
                    self.signals[encoding_link[name]]['encoding'] = self._parse_encoding(\
                        encoding_data_text[ed_start:_end])
                    for key in self.frames.keys():
                        if encoding_link[name] in self.frames[key]['signals'].keys():
                               self.frames[key]['signals'][encoding_link[name]]['encoding'] = \
                                                self.signals[encoding_link[name]]['encoding']
                ed_start = _end+1
            else:
                break

    def _parse_encoding(self, text):
        """
        parses the encoding into logical and physical values
        if the value is physical, we record the maximum and minimum
        if the value is logical, we record each numeric value and what
        it represents
        """
        lines = text.split(';')
        raw = {}
        if 'logical_value' in lines[0]:
            raw['type'] = 'logical'
            for line in lines:
                if line.strip():
                    value, data = line.split(',')[1:3]
                    raw[int(value, 0)] = data.replace('"', '').replace("'", '').strip()
        else:
            raw['type'] = 'physical'
            raw['min'], raw['max'] = map(int, lines[0].split(',')[1:3])
        return raw

    def _parse_signal(self, signal):
        """parse the signals into name, size, init value, publisher and subscribers if supplied"""
        regex = re.compile(r"\s*(\w+)\s*:\s*([1-9]\d?)\s*,\s*({.+}|-?\d+|0[xX][0-9a-fA-F]+)\s*,\s*(\w+)\s*(?:$|\s*,(\w+))")
        m = regex.match(signal)
        if m and len(m.groups()) in [4, 5]:
            groups = m.groups()
            name = groups[0]
            raw = {}
            raw['size'] = int(groups[1], 0)
            raw['publisher'] = groups[3]
            raw['subscriber'] = groups[4] if len(groups) == 5 else ""
            init = groups[2]
            if init[0] == '{' and init[-1] == '}':
                raw['init'] = [int(v, 0) for v in init[1:-1].split(',')]
                pass
            else:
                raw['init'] = int(init, 0)

            for key in self.frames.keys():
                if name in self.frames[key]['signals'].keys():
                    #our signal is in this frame, so update its data
                    self.frames[key]['signals'][name]['init_value'] = raw['init']
                    self.frames[key]['signals'][name]['size'] = raw['size']
                    
            self.signals[name] = raw
        else:
            # invalid signal
            pass

    def _parse_all_frames(self, start, end):
        """initiates the parsing of all frames"""
        frames = self.all_text[start:end].replace('\n', '').split('}')
        frames = trim(frames)
        for frame in frames:
            if frame.strip():
                self._parse_frame(frame)

    def _parse_frame(self, frame):
        """parses frames into name, id, publisher, length, and composing signals with offsets"""
        frame_data, signals = frame.split('{')
        raw = {}
        name, frame_header = frame_data.split(':')
        data = frame_header.split(',')
        raw['id'] = int(data[0], 0)
        raw['publisher'] = data[1]
        raw['len'] = int(data[2], 0)
        signals = signals.split(";")
        raw['signals'] = {}
        for signal in signals:
            if signal.strip():
                data = signal.split(',')
                raw['signals'][data[0]] = {'offset':int(data[1], 0)}
        self.frames[name] = raw

    def _parse_all_attributes(self, start, end):
        """initiates the parsing of all node attributes"""
        text = self.all_text[start:end].replace('\n', '').replace(' ', '')
        end = len(text)
        start = 0
        while start not in (end, -1):
            name = text[start:text.find('{', start)]
            start, _end = self._find_ends(name, text)
            self.attributes[name] = self._parse_attributes(text[start:_end])
            start = _end

    def _parse_attributes(self, attributes):
        """parses an node's attributes"""
        start, end = self._find_ends('configurable_frames', attributes)
        config_frames = attributes[start:end].split(';')
        raw = {}
        #remove configurable frames since we already have the data
        attributes = attributes.replace(attributes[attributes.find('configurable'):end+1], '')
        data = attributes.split(';')
        for line in data:
            if line.strip():
                name, value = line.split('=')
                if name.lower() == 'product_id':
                    value = value.split(',')
                raw[name] = value

        raw['configurable_frames'] = {}

        for frame in config_frames:
            if frame.strip():
                if len(frame.split('=')) == 2:
                    #LIN 2.0
                    name, _id = frame.split('=')
                    raw['configurable_frames'][name] = _id
                else:
                    #LIN 2.1>
                    raw['configurable_frames'][name] = ""

        return raw

    def get_nodes(self):
        """return all nodes"""
        return self.nodes

    def get_signals(self):
        """return all signals"""
        return self.signals

    def get_signals_by_publish_node(self, node):
        """return all signals for a given node"""
        data = {}
        for key, val in self.signals:
            if val['publisher'] == node:
                data[key] = val
        return data

    def get_frames(self):
        """return all frames"""
        return self.frames

    def get_frames_by_publish_node(self, node):
        """return all frames for a given publisher node"""
        data = {}
        for key, val in self.frames:
            if val['publisher'] == node:
                data[key] = val
        return data

    def get_node_attributes(self):
        """return all node attributes"""
        return self.attributes

    def get_attributes_by_node(self, node):
        """Return attributes for a specific node"""
        if node in self.attributes.keys():
            return self.attributes[node]
        return None

    def get_all(self):
        """return all parsed data"""
        data = {
            "attributes" : self.attributes,
            "nodes" : self.nodes,
            "frames" : self.frames,
            "signals" : self.signals}
        return data
    
if __name__=='__main__':
    path = r'C:\example_file_here.ldf'
    parser = LDFParser(path)
    print(parser.get_all())
