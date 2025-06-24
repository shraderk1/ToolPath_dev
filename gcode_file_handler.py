from gcode_models import GCodeDocument
# GCodeParser will be imported by the main application and passed to the handler.

class GCodeFileHandler:
    def __init__(self, parser):
        """
        Initializes the GCodeFileHandler with a GCodeParser instance.
        :param parser: An instance of GCodeParser.
        """
        self.parser = parser

    def load_gcode_file(self, file_path):
        """
        Loads a G-code file, processes it, and returns a GCodeDocument object.
        """
        doc = GCodeDocument(file_path=file_path)
        try:
            with open(file_path, 'r', encoding='utf-8') as file: # Specify encoding
                doc.raw_lines = file.readlines()
        except Exception as e:
            raise IOError(f"Failed to read file: {file_path}. Error: {e}")

        doc.cleaned_lines = self.parser.remove_thumbnails(doc.raw_lines)

        # The parser will populate the document's layers and layer_indices
        self.parser.parse_document_to_layers(doc.cleaned_lines, doc)

        return doc

    def save_gcode_document(self, document, output_file_path, edited_layer_indices=None):
        """
        Saves the GCodeDocument to a specified file path.
        If edited_layer_indices is provided, it indicates which layers in document.layers
        contain edits (their .items list is the source of truth). Otherwise, original lines are used.

        :param document: The GCodeDocument object to save.
        :param output_file_path: Path to save the G-code file.
        :param edited_layer_indices: A set or list of document layer indices that have been edited.
                                     The GCodeLayer.items for these layers will be serialized.
        """
        if edited_layer_indices is None:
            edited_layer_indices = set()

        final_gcode_to_write = []

        # This saving logic needs to correctly interleave header, layer content (original or edited),
        # lines between layers, and footer.
        # It uses `document.cleaned_lines` as the backbone and substitutes layer content.

        current_cleaned_line_idx = 0
        num_layers_in_doc = document.layer_count

        for i in range(num_layers_in_doc):
            layer_obj = document.get_layer_by_document_index(i)
            if not layer_obj:
                # This should not happen if document is consistent
                continue

            layer_start_in_cleaned = document.layer_indices_in_cleaned_lines[i]

            # Add lines from cleaned_lines that are before this layer's official start
            if current_cleaned_line_idx < layer_start_in_cleaned:
                final_gcode_to_write.extend(document.cleaned_lines[current_cleaned_line_idx:layer_start_in_cleaned])

            # Now process the layer itself
            if i in edited_layer_indices:
                # This layer was edited, so serialize its .items list
                layer_lines = self.parser.gcode_layer_to_lines(layer_obj)
                final_gcode_to_write.extend(layer_lines)
            else:
                # Layer was not edited, use its original_lines from GCodeLayer object
                # (which should be a segment of cleaned_lines including its ;LAYER_CHANGE)
                final_gcode_to_write.extend(layer_obj.original_lines)

            # Update current_cleaned_line_idx to point to the line after this layer's original segment
            # The length of the original layer segment is len(layer_obj.original_lines)
            current_cleaned_line_idx = layer_start_in_cleaned + len(layer_obj.original_lines)

        # Add any remaining lines from cleaned_lines (footer or content after the last processed layer)
        if current_cleaned_line_idx < len(document.cleaned_lines):
            final_gcode_to_write.extend(document.cleaned_lines[current_cleaned_line_idx:])

        # If no layers were defined (e.g. empty file or file without ;LAYER_CHANGE and parser treated as no layers)
        if num_layers_in_doc == 0 and document.cleaned_lines:
             final_gcode_to_write.extend(document.cleaned_lines)


        try:
            with open(output_file_path, 'w', encoding='utf-8') as file: # Specify encoding
                file.writelines(final_gcode_to_write)
        except Exception as e:
            raise IOError(f"Failed to write file: {output_file_path}. Error: {e}")
