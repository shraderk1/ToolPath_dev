from gcode_models import Move, GCodeLayer

class GCodeParser:
    def __init__(self):
        pass

    def remove_thumbnails(self, lines):
        """Removes thumbnail sections from G-code lines."""
        cleaned = []
        skip = False
        for line in lines:
            line_stripped = line.strip()
            if 'thumbnail_QOI begin' in line_stripped or 'thumbnail begin' in line_stripped:
                skip = True
                continue
            if 'thumbnail_QOI end' in line_stripped or 'thumbnail end' in line_stripped:
                skip = False
                continue
            if not skip:
                cleaned.append(line)
        return cleaned

    def parse_document_to_layers(self, cleaned_gcode_lines, gcode_document):
        """
        Parses cleaned G-code lines, populates the GCodeDocument with GCodeLayer objects,
        and stores the start indices of these layers.
        Non-layer lines (header, footer, lines between layers) remain in GCodeDocument.cleaned_lines.
        """
        gcode_document.layers = []
        gcode_document.layer_indices_in_cleaned_lines = []

        current_layer_original_lines = []
        layer_counter_in_doc = 0 # This will be the index in GCodeDocument.layers

        # Initial pass to find all ;LAYER_CHANGE markers and segment the document
        # This simplified approach assumes layers are contiguous blocks starting with ;LAYER_CHANGE
        # or the whole file is one layer if no such markers.

        last_layer_change_idx = -1
        for i, line_text in enumerate(cleaned_gcode_lines):
            line_strip = line_text.strip()
            if line_strip == ';LAYER_CHANGE':
                if last_layer_change_idx != -1: # Found a previous layer change, so current_layer_original_lines is for that layer
                    # The lines from last_layer_change_idx up to i-1 form a layer's content.
                    # The GCodeLayer object should store its lines *including* its initial ';LAYER_CHANGE'
                    layer_obj = GCodeLayer(layer_index_in_document=layer_counter_in_doc,
                                           original_lines=cleaned_gcode_lines[last_layer_change_idx:i])
                    self._parse_layer_lines_to_items(layer_obj)
                    gcode_document.add_layer(layer_obj)
                    gcode_document.layer_indices_in_cleaned_lines.append(last_layer_change_idx)
                    layer_counter_in_doc += 1
                last_layer_change_idx = i # Current ';LAYER_CHANGE' is the start of a new layer segment

        # Handle the last layer segment (after the final ';LAYER_CHANGE' or if no ';LAYER_CHANGE' at all)
        if last_layer_change_idx != -1: # If there was at least one ';LAYER_CHANGE'
            # Content from the last ';LAYER_CHANGE' to the end of the file
            layer_obj = GCodeLayer(layer_index_in_document=layer_counter_in_doc,
                                   original_lines=cleaned_gcode_lines[last_layer_change_idx:])
            self._parse_layer_lines_to_items(layer_obj)
            gcode_document.add_layer(layer_obj)
            gcode_document.layer_indices_in_cleaned_lines.append(last_layer_change_idx)
        elif cleaned_gcode_lines: # No ';LAYER_CHANGE' found, treat entire file as one layer
            layer_obj = GCodeLayer(layer_index_in_document=0, original_lines=list(cleaned_gcode_lines))
            self._parse_layer_lines_to_items(layer_obj)
            gcode_document.add_layer(layer_obj)
            gcode_document.layer_indices_in_cleaned_lines.append(0) # Starts at line 0

        # `gcode_document.cleaned_lines` remains the full list of lines.
        # `gcode_document.layers` contains GCodeLayer objects, each with their `original_lines` subset.
        # `gcode_document.layer_indices_in_cleaned_lines` marks where each layer starts in `cleaned_lines`.

    def _parse_layer_lines_to_items(self, gcode_layer):
        """
        Parses the original_lines of a GCodeLayer into a list of items (Move objects or string lines).
        Populates gcode_layer.items.
        """
        gcode_layer.items = []
        x = y = z = e = None  # Current absolute coordinates
        last_x = last_y = last_z = last_e = None # Last coordinates *on a move line*

        # Relative extrusion state (G91 E) is not handled here, assuming absolute (G90 E)
        # PrusaSlicer uses absolute E by default.

        current_type_comment_line = None # Stores the most recent ';TYPE:...' line encountered

        for line_idx, line_text in enumerate(gcode_layer.original_lines):
            line_strip = line_text.strip()

            if not line_strip: # Empty line
                gcode_layer.add_item(line_text) # Preserve empty lines
                continue

            if line_strip.startswith(';TYPE:'):
                current_type_comment_line = line_text # Store it, will be added before the next G1 move
                gcode_layer.add_item(line_text) # Add ;TYPE comment as a string item itself
                continue

            # For other comments or M-codes, G-codes not G0-G3: add as string item
            if line_strip.startswith(';') or \
               line_strip.startswith('M') or \
               line_strip.startswith('T') or \
               line_strip.startswith('G28') or \
               line_strip.startswith('G90') or line_strip.startswith('G91') or \
               line_strip.startswith('G92'): # Add more non-move G-codes as needed
                gcode_layer.add_item(line_text)
                current_type_comment_line = None # Reset type comment if a non-G1/G0 command appears
                continue

            # Attempt to parse G0, G1, G2, G3 as moves
            # G2/G3 (arcs) are complex and will be treated as single moves from start to end point for now.
            if line_strip.startswith(('G0', 'G1', 'G00', 'G01', 'G2', 'G02', 'G3', 'G03')):
                parts = line_strip.split()
                cmd = parts[0].upper()

                move_params = {'x': None, 'y': None, 'z': None, 'e': None, 'f': None, 'i': None, 'j': None, 'r':None, 'p':None, 's':None}
                has_xyz_change = False # Did X, Y, or Z change in this line?
                has_e_change = False   # Did E change in this line?

                for part in parts[1:]:
                    if not part: continue
                    char = part[0].upper()
                    try:
                        value = float(part[1:])
                        if char == 'X': move_params['x'] = value; has_xyz_change = True
                        elif char == 'Y': move_params['y'] = value; has_xyz_change = True
                        elif char == 'Z': move_params['z'] = value; has_xyz_change = True # Z change doesn't make it a "move" for type determination alone
                        elif char == 'E': move_params['e'] = value; has_e_change = True
                        elif char == 'F': move_params['f'] = value
                        # For G2/G3, capture I, J, R, P, S if needed for more detailed parsing later
                        elif char == 'I': move_params['i'] = value
                        elif char == 'J': move_params['j'] = value
                        elif char == 'R': move_params['r'] = value
                        elif char == 'P': move_params['p'] = value # G2/G3 P parameter (revolutions)
                        elif char == 'S': move_params['s'] = value # G0 S parameter (Laser power for some firmware)
                    except ValueError:
                        # Non-numeric parameter or malformed, treat line as non-move
                        # This path should ideally not be taken for valid G-code.
                        # For simplicity, if parsing fails, we might misclassify.
                        pass

                # If it's just G0/G1 without parameters, or only F/S, it's not a spatial move.
                if not has_xyz_change and not has_e_change and cmd in ('G0','G1','G00','G01'):
                    gcode_layer.add_item(line_text) # Add as a string item
                    current_type_comment_line = None
                    continue

                # Determine current absolute coordinates for the move
                # If a coordinate is not specified in the line, it retains its previous value.
                current_x = move_params['x'] if move_params['x'] is not None else last_x
                current_y = move_params['y'] if move_params['y'] is not None else last_y
                current_z = move_params['z'] if move_params['z'] is not None else last_z
                current_e = move_params['e'] if move_params['e'] is not None else last_e

                # Determine move type (e.g., 'travel' or from ';TYPE:' comment)
                # This logic is from the original GCodeEditor.parse_moves and Layer3DViewer.parse_moves
                move_type_str = None
                if current_type_comment_line:
                    # Extract type from comment like ";TYPE:External perimeter"
                    type_from_comment = current_type_comment_line.strip()[6:].lower() # Get "external perimeter"
                    move_type_str = type_from_comment

                # Override with 'travel' if it's a non-extruding move (G0 or G1 with no E change or E reset)
                # A G0 command is typically always travel, regardless of E.
                # A G1 move is travel if E does not advance or is not present.
                is_explicit_travel_cmd = cmd in ('G0', 'G00')

                # Extrusion amount for this move. If E is specified, it's current_e - last_e.
                # If E is not specified, extrusion_amount is 0.
                extrusion_this_move = 0.0
                if move_params['e'] is not None and last_e is not None: # E is specified
                    extrusion_this_move = current_e - last_e
                elif move_params['e'] is not None and last_e is None: # First E value
                    extrusion_this_move = current_e # Or treat as relative to 0 if E was reset

                # Threshold for "significant" extrusion. Helps classify moves with tiny E changes due to float precision as travel.
                significant_extrusion_threshold = 1e-5 # 0.00001 mm

                if is_explicit_travel_cmd:
                    move_type_str = 'travel'
                elif abs(extrusion_this_move) < significant_extrusion_threshold and has_xyz_change : # G1, E not changed much or not present, but XYZ changed
                    move_type_str = 'travel'
                elif not has_e_change and last_e is None and has_xyz_change: # No E ever seen, G1 with XYZ change
                    move_type_str = 'travel'


                # Create Move object
                # A "move" for visualization typically requires X or Y to change.
                # Z-only or E-only moves are also valid G-code but might be treated differently by visualizers.
                if current_x is not None and current_y is not None: # Requires at least X and Y to be defined
                    move_obj = Move(
                        x=current_x, y=current_y, z=current_z, e=current_e,
                        move_type=move_type_str,
                        original_line_index=line_idx,
                        preceding_comment=current_type_comment_line if move_type_str and move_type_str != 'travel' else None
                    )
                    gcode_layer.add_item(move_obj)

                    # Update last known absolute coordinates for next iteration
                    if move_params['x'] is not None: last_x = current_x
                    if move_params['y'] is not None: last_y = current_y
                    if move_params['z'] is not None: last_z = current_z
                    if move_params['e'] is not None: last_e = current_e

                    current_type_comment_line = None # Consume the type comment
                else:
                    # Not considered a plottable XY move (e.g., G1 Z5 only, or G1 E10 only without prior X,Y)
                    # Add as a string item. This might need refinement.
                    gcode_layer.add_item(line_text)
                    current_type_comment_line = None

            else: # Line is not a G0-G3, comment, M-code, etc. (should be rare for valid G-code)
                gcode_layer.add_item(line_text) # Treat as a non-move line
                current_type_comment_line = None

        # After parsing all lines, gcode_layer.items is populated.

    def gcode_layer_to_lines(self, gcode_layer):
        """
        Converts a GCodeLayer object's items (Move objects and strings) back into a list of G-code line strings.
        """
        output_lines = []
        last_e_val_written_to_gcode = None # Tracks the E value of the last G1 line that had an E parameter

        for item in gcode_layer.items:
            if isinstance(item, str):
                output_lines.append(item) # Assumes item includes newline if it's a full line
            elif isinstance(item, Move):
                move_dict = item.to_dict() # Convert Move object to dictionary for processing

                # Reconstruct the G-code line from the Move object
                # This needs to handle whether to write X, Y, Z, E based on changes from a "previous" state.
                # However, for saving, we usually write the explicit parameters stored in the Move object.
                # The main complexity is the E value: only write if different from last written E.

                # Prepend preceding comment if it was stored with the move and not already added as a string item.
                # The current _parse_layer_lines_to_items adds ;TYPE as string, so this might be redundant
                # if item.preceding_comment and item.preceding_comment not in output_lines[-1]: # Basic check
                #    output_lines.append(item.preceding_comment)

                x_str = f"X{move_dict['x']:.3f}" if move_dict['x'] is not None else ''
                y_str = f"Y{move_dict['y']:.3f}" if move_dict['y'] is not None else ''
                z_str = f"Z{move_dict['z']:.3f}" if move_dict['z'] is not None else ''
                e_str = ''

                # Logic for E value from original GCodeEditor.moves_to_gcode
                if move_dict.get('type') == 'travel':
                    # For travel moves, no E parameter is written.
                    # The extruder holds its position from the last extrusion.
                    # The move_dict['e'] should still reflect this logical extruder position.
                    pass # e_str remains empty
                else: # Non-travel (presumably extrusion)
                    if move_dict['e'] is not None:
                        current_move_logical_e = move_dict['e']
                        # Write E only if it's different from the last *written* E value,
                        # or if no E has been written yet in this sequence of moves.
                        if last_e_val_written_to_gcode is None or \
                           abs(current_move_logical_e - last_e_val_written_to_gcode) > 1e-5: # Use tolerance for float comparison
                            e_str = f"E{current_move_logical_e:.5f}"
                            last_e_val_written_to_gcode = current_move_logical_e
                        # If E is same as last written, e_str remains empty (no redundant E parameter)
                    # If a non-travel move has no 'e' in its dictionary (e.g., a G1 Z-only move without E change),
                    # e_str remains empty, which is correct.

                # Construct the G-code line. Assume G1 for all moves from Move objects for now.
                # More sophisticated would be to store original command (G0/G1/G2/G3) in Move object.
                gline_parts = ["G1"] # Default to G1
                if x_str: gline_parts.append(x_str)
                if y_str: gline_parts.append(y_str)
                if z_str: gline_parts.append(z_str)
                if e_str: gline_parts.append(e_str)

                # Only add the line if it's more than just "G1" (i.e., it has parameters)
                if len(gline_parts) > 1:
                    output_lines.append(" ".join(gline_parts) + '\n')
                # If the line was just "G1" but it was supposed to be an E-only move where E didn't change,
                # it's correctly omitted. If it was a travel move with no X,Y,Z change, it's also omitted.
            else:
                # Unknown item type in gcode_layer.items
                pass # Or raise error

        return output_lines

    def _format_move_as_gcode_line(self, move_dict, last_e_written):
        """
        (This is a helper, similar to logic inside gcode_layer_to_lines, kept for potential direct use if needed)
        Formats a single move dictionary into a G-code line string.
        `move_dict` is like {'x': ..., 'y': ..., 'z': ..., 'e': ..., 'type': ...}
        `last_e_written` is the last E value that was actually written to a G-code line.
        Returns the G-code string (with newline), or None if the line is empty or invalid.
        """
        m = move_dict
        x_str = f"X{m['x']:.3f}" if 'x' in m and m['x'] is not None else ''
        y_str = f"Y{m['y']:.3f}" if 'y' in m and m['y'] is not None else ''
        z_str = f"Z{m['z']:.3f}" if 'z' in m and m['z'] is not None else ''
        e_str = ''

        if m.get('type') != 'travel':
            if 'e' in m and m['e'] is not None:
                current_move_e_val = m['e']
                if last_e_written is None or abs(current_move_e_val - last_e_written) > 1e-5:
                    e_str = f"E{current_move_e_val:.5f}"

        # Assume G1, original command (G0/G1/G2/G3) could be stored in Move object for more fidelity
        gline_parts = ["G1"]
        if x_str: gline_parts.append(x_str)
        if y_str: gline_parts.append(y_str)
        if z_str: gline_parts.append(z_str)
        if e_str: gline_parts.append(e_str)

        if len(gline_parts) > 1:
            return " ".join(gline_parts) + '\n'
        return None
