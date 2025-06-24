class Move:
    def __init__(self, x=None, y=None, z=None, e=None, move_type=None, original_line_index=None, preceding_comment=None):
        self.x = x
        self.y = y
        self.z = z
        self.e = e
        self.type = move_type  # e.g., 'travel', 'perimeter', 'external_perimeter' or from ;TYPE comment
        self.original_line_index = original_line_index # Original index within its GCodeLayer.original_lines
        self.preceding_comment = preceding_comment # Stores the ;TYPE comment line if it directly precedes this move

    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'z': self.z,
            'e': self.e,
            'type': self.type,
            'original_line_index': self.original_line_index,
            'preceding_comment': self.preceding_comment,
        }

    @staticmethod
    def from_dict(data):
        return Move(
            x=data.get('x'),
            y=data.get('y'),
            z=data.get('z'),
            e=data.get('e'),
            move_type=data.get('type'),
            original_line_index=data.get('original_line_index'),
            preceding_comment=data.get('preceding_comment')
        )

class GCodeLayer:
    def __init__(self, layer_index_in_document, original_lines=None):
        self.layer_index_in_document = layer_index_in_document # The 0-based index in the GCodeDocument's list of layers
        self.original_lines = original_lines if original_lines is not None else [] # Raw lines for this layer as parsed

        # `items` will store the sequence of operations for this layer.
        # Each item can be a Move object or a string (for non-move G-code lines).
        # This list represents the editable, final sequence for the layer.
        self.items = []
        # self.moves = [] # List of Move objects, derived from items or used to build items.
        # self.non_move_lines = {} # map of original_line_index (in original_lines) : line_text

    def add_item(self, item):
        self.items.append(item)

    def get_moves(self):
        """Returns a list of Move objects from self.items."""
        return [item for item in self.items if isinstance(item, Move)]

    def get_non_move_line_strings(self):
        """Returns a list of non-move line strings from self.items."""
        return [item for item in self.items if isinstance(item, str)]


class GCodeDocument:
    def __init__(self, file_path=None):
        self.file_path = file_path
        self.raw_lines = [] # All lines as read from the file
        self.cleaned_lines = [] # Lines after initial processing like thumbnail removal

        # `layers` stores GCodeLayer objects.
        self.layers = [] # List of GCodeLayer objects, ordered as they appear in the file.

        # `layer_indices_in_cleaned_lines` stores the starting line number (0-based)
        # in `self.cleaned_lines` for each corresponding layer in `self.layers`.
        # This helps in reconstructing the file, especially parts between layers or header/footer.
        self.layer_indices_in_cleaned_lines = []

    def add_layer(self, layer):
        self.layers.append(layer)

    def get_layer_by_document_index(self, index):
        if 0 <= index < len(self.layers):
            return self.layers[index]
        return None

    @property
    def layer_count(self):
        return len(self.layers)
