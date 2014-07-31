from swirlypy.question import ShellQuestion
from swirlypy.questions.GetValue import CaptureExprs, Recorder
import code, ast, sys, abc
from copy import deepcopy
from swirlypy.dictdiffer import DictDiffer

class RecordingQuestion(ShellQuestion):
    
    # Mark this class as an abstract.
    __metaclass__ = abc.ABCMeta

    _required_ = [ ] # Required fields will depend on subclass
     
    def get_response(self, data={}):
        """Interacts with the user until broken from, or reaches EOF.
        Each new command that the user enters is captured and yielded to
        the caller."""
        console = self.new_console(data)
        for value in console.interact(""):
            yield value
      
    @abc.abstractmethod       
    def test_response(self, response, data={}):
        """"""
    
    def execute(self, data={}):
        self.print()
         
        # Loop until we get the correct answer.
        while True:
            # If data does not contain a lesson state, create one
            if not "state" in data:
                data["state"] = dict()
            # To avoid corruption through user errors the user should not be given 
            # direct access to the state. Hence, make a deep copy.
            dcp = deepcopy(data["state"])
            # Get any values that the user generates, and pass them to
            # test_response.
            for value in self.get_response(data=dcp):
                if self.test_response(value, data=dcp):
                    # Since test was passed, modify and return the data
                    data["state"].update(value["added"])
                    data["state"].update(value["changed"])
                    for k in value["removed"]:
                        del data["state"][k]
                    return data
                else:
                    try:
                        self.print_help(self.hint)
                    except AttributeError:
                        pass

    def new_console(self, locals):
        """Creates a new recording console and recorder, and includes the recorder
        as __swirlypy_recorder__ in the new console."""
        # Create the new recorder.
        # XXX: This is also a bit hacky. The recorder should be handled
        # entirely by the VPC.
        self._recorder = Recorder()
        newlocals = locals.copy()
        newlocals["__swirlypy_recorder__"] = self._recorder
        return RecordingConsole(newlocals)

class RecordingConsole(code.InteractiveConsole):
    """Allows the user to interact with a console, and yields every
    command that they type in as an AST."""

    class RecorderCorruptedException(Exception): pass
     
    def compile_ast(self, source, filename = "<input>", symbol = "single"):
        # Here, we try to compile the relevant code. It may throw an
        # exception indicating that the command is not complete, in
        # which case we cannot proceed, but a full command will be
        # supplied eventually.
        compiled = code.compile_command(source, filename, symbol)
         
        # If the compilation succeeded, as indicated by its object not being
        # None, and no exception having occurred, parse it with AST and
        # store that.
        if compiled != None:
            self.latest_parsed = ast.parse(source, filename, symbol)
            CaptureExprs().visit(self.latest_parsed)
            # Since latest_parsed has been altered to capture values computed
            # but not assigned, store an unaltered copy for testing.
            self.clean_parsed = ast.parse(source, filename, symbol)
            
        return compile(self.latest_parsed, filename, symbol)
        
    def interact(self, banner=None):
        """Interacts with the user. Each time a complete command is
        entered, it is parsed using AST and yielded."""
         
        # XXX: This is a hack to override parent precedence. This needs
        # to be fixed in a better way.
        self.compile = self.compile_ast
         
        # Borrow a block of code from code.InteractiveConsole
        try:
            sys.ps1
        except AttributeError:
            sys.ps1 = ">>> "
        try:
            sys.ps2
        except AttributeError:
            sys.ps2 = "... "
        cprt = 'Type "help", "copyright", "credits" or "license" for more information.'
        if banner is None:
            self.write("Python %s on %s\n%s\n(%s)\n" %
                      (sys.version, sys.platform, cprt,
                       self.__class__.__name__))
        elif banner:
            self.write("%s\n" % str(banner))
        more = 0
        while 1:
            # Reset the value of latest_parsed.
            self.latest_parsed = None
            # Make a copy of locals
            cpylocals = self.locals.copy()
             
            try:
                if more:
                    prompt = sys.ps2
                else:
                    prompt = sys.ps1
                try:
                    line = self.raw_input(prompt)
                except EOFError:
                    self.write("\n")
                    break
                else:
                    more = self.push(line)
                    # A DictDiffer object has 4 fields: added, changed, removed, unchanged,
                    # These are sets containing variable names only. Attaching values:
                    diffs = DictDiffer(self.locals, cpylocals)
                    ad =dict()
                    for k in diffs.added()-{'__builtins__'}:
                        ad[k] = self.locals[k]
                    ch= dict()
                    for k in diffs.changed():
                        ch[k] = self.locals[k]
                    rv = dict()
                    for k in diffs.removed():
                        rv[k] = cpylocals[k]
                    # Check to see if a new value has been parsed yet.
                    # If so, yield various useful things. 
                    if self.latest_parsed != None:
                        yield {"ast":self.clean_parsed,  "added":ad, "changed":ch, \
                        "removed":rv, "values":self.locals["__swirlypy_recorder__"]}
                         
            except KeyboardInterrupt:
                self.write("\nKeyboardInterrupt\n")
                self.resetbuffer()
                more = 0
