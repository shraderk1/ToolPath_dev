import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QStatusBar, QLabel,
    QListWidget, QAbstractItemView, QHBoxLayout, QDialog, QSlider, QGridLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import os
import pyqtgraph.opengl as gl
import pyqtgraph as pg
import numpy as np

# Import new classes
from gcode_models import GCodeDocument, Move, GCodeLayer
from gcode_parser import GCodeParser
from gcode_file_handler import GCodeFileHandler


viewer_open_count = 0

class GCodeEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Printing Toolpath (G-code) Editor (Refactored)")
        self.setGeometry(100, 100, 650, 350)

        # Data handling attributes
        self.gcode_document = None  # Will hold GCodeDocument object
        self.selected_doc_layer_indices = set()  # Stores indices of layers in GCodeDocument.layers list

        # Viewer dialog instance
        self.viewer_dialog = None

        # Dictionary to store pending edits from the viewer before saving the document
        # Key: document layer index (integer)
        # Value: The GCodeLayer.items list (containing Move objects and strings) after editing in viewer
        self.pending_layer_item_edits = {}

        # Instantiate parser and handler
        self.gcode_parser = GCodeParser()
        self.gcode_file_handler = GCodeFileHandler(self.gcode_parser)

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setAlignment(Qt.AlignCenter)

        self.info_label = QLabel("No G-code file selected.")
        self.info_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(10)
        self.info_label.setFont(font)
        main_layout.addWidget(self.info_label)

        btn_layout = QHBoxLayout()
        self.open_button = QPushButton("Select G-code File")
        self.open_button.setMinimumHeight(32)
        self.open_button.setFont(QFont('Arial', 11))
        self.open_button.clicked.connect(self.open_gcode_file_action) # Renamed method
        btn_layout.addWidget(self.open_button)

        self.save_button = QPushButton("Save As")
        self.save_button.setMinimumHeight(32)
        self.save_button.setFont(QFont('Arial', 11))
        self.save_button.clicked.connect(self.save_gcode_file_action) # Renamed method
        self.save_button.setEnabled(False)
        btn_layout.addWidget(self.save_button)

        self.layer_button = QPushButton("Select Layers")
        self.layer_button.setMinimumHeight(32)
        self.layer_button.setFont(QFont('Arial', 11))
        self.layer_button.clicked.connect(self.show_layer_selector_action) # Renamed method
        self.layer_button.setEnabled(False)
        btn_layout.addWidget(self.layer_button)

        self.view_layer_button = QPushButton("View Layer 3D")
        self.view_layer_button.setMinimumHeight(32)
        self.view_layer_button.setFont(QFont('Arial', 11))
        self.view_layer_button.clicked.connect(self.view_selected_layer_action) # Renamed method
        self.view_layer_button.setEnabled(False)
        btn_layout.addWidget(self.view_layer_button)

        main_layout.addLayout(btn_layout)
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def open_gcode_file_action(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select G-code File", "", "G-code Files (*.gcode *.nc *.txt);;All Files (*)")
        if file_path:
            try:
                self.gcode_document = self.gcode_file_handler.load_gcode_file(file_path)
                filename = os.path.basename(file_path)
                self.info_label.setText(f"Selected: {filename}")
                self.save_button.setEnabled(True)
                self.status_bar.showMessage(f"Selected: {filename}")

                self.layer_button.setEnabled(bool(self.gcode_document and self.gcode_document.layer_count > 0))
                self.selected_doc_layer_indices = set()
                self.view_layer_button.setEnabled(False)
                self.pending_layer_item_edits = {} # Clear pending edits from previous file

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load or parse file: {e}")
                self.gcode_document = None
                self.save_button.setEnabled(False)
                self.layer_button.setEnabled(False)
                self.view_layer_button.setEnabled(False)
                self.info_label.setText("Error loading file.")
                self.status_bar.showMessage(f"Error: {e}")
        else:
            self.status_bar.showMessage("No file selected.")

    def show_layer_selector_action(self):
        if not self.gcode_document or self.gcode_document.layer_count == 0:
            QMessageBox.warning(self, "Warning", "No layers found in the G-code file.")
            return

        # Labels for the dialog (e.g., "Layer 0 (Doc Idx 0)", "Layer 1 (Doc Idx 1)", ...)
        # GCodeLayer.layer_index_in_document is the true index.
        layer_labels = [f"Layer {idx} (File Layer {layer.layer_index_in_document})"
                        for idx, layer in enumerate(self.gcode_document.layers)]

        # Pass current selection (indices into the document.layers list)
        dlg = LayerSelectorDialog(layer_labels, self.selected_doc_layer_indices, self)
        if dlg.exec_():
            self.selected_doc_layer_indices = dlg.get_selected_layers() # These are indices for document.layers

            if not self.selected_doc_layer_indices:
                self.view_layer_button.setEnabled(False)
                self.status_bar.showMessage("No layers selected.")
            elif len(self.selected_doc_layer_indices) == 1:
                self.view_layer_button.setEnabled(True)
                doc_idx = list(self.selected_doc_layer_indices)[0]
                self.status_bar.showMessage(f"Selected layer: Document Index {doc_idx}")
            else: # Multiple layers selected
                self.view_layer_button.setEnabled(False) # Viewer only shows one layer
                self.status_bar.showMessage(f"Selected {len(self.selected_doc_layer_indices)} layers (for potential future multi-layer ops).")
        else: # Dialog cancelled
            pass


    def save_gcode_file_action(self):
        if not self.gcode_document:
            QMessageBox.warning(self, "Warning", "No G-code document loaded.")
            return

        # Apply any pending edits from self.pending_layer_item_edits to the self.gcode_document.layers[*].items
        edited_layer_indices_for_save = set()
        for doc_layer_idx, edited_items_list in self.pending_layer_item_edits.items():
            if 0 <= doc_layer_idx < self.gcode_document.layer_count:
                gcode_layer_obj = self.gcode_document.get_layer_by_document_index(doc_layer_idx)
                if gcode_layer_obj:
                    gcode_layer_obj.items = edited_items_list # Replace items with edited version
                    edited_layer_indices_for_save.add(doc_layer_idx)

        suggested_path = self.gcode_document.file_path if self.gcode_document.file_path else ""
        file_path, _ = QFileDialog.getSaveFileName(self, "Save G-code File As", suggested_path, "G-code Files (*.gcode *.nc *.txt);;All Files (*)")

        if file_path:
            try:
                # Pass the set of indices for layers whose .items should be used by the saver
                self.gcode_file_handler.save_gcode_document(self.gcode_document, file_path, edited_layer_indices_for_save)
                self.status_bar.showMessage(f"Saved: {file_path}")
                QMessageBox.information(self, "Saved", f"G-code saved to {file_path}")
                # Optionally, clear pending edits after successful save to prevent re-applying them if save is called again
                # self.pending_layer_item_edits = {}
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file: {e}")
                self.status_bar.showMessage(f"Error saving file: {e}")
        else:
            self.status_bar.showMessage("Save operation cancelled.")


    def view_selected_layer_action(self):
        if len(self.selected_doc_layer_indices) != 1:
            QMessageBox.warning(self, "Warning", "Please select exactly one layer to view/edit.")
            return

        doc_layer_idx = list(self.selected_doc_layer_indices)[0]
        gcode_layer_obj = self.gcode_document.get_layer_by_document_index(doc_layer_idx)

        if not gcode_layer_obj:
            QMessageBox.critical(self, "Error", f"Could not retrieve layer at document index {doc_layer_idx}.")
            return

        # Determine the items to pass to the viewer:
        # If there are pending edits for this layer, use those. Otherwise, use items from the parsed GCodeLayer.
        layer_items_for_viewer = self.pending_layer_item_edits.get(doc_layer_idx, gcode_layer_obj.items)

        # The viewer expects a list of move dictionaries for its `moves_override`
        # and a map of non-move lines (which is not directly used by current viewer but good to have).
        # Convert GCodeLayer.items (Move objects and strings) to list of move dicts for viewer.
        # Non-move strings from items are implicitly handled by their presence in the item list.

        moves_for_viewer_dicts = []
        # The Layer3DViewerDialog's `parse_moves` (which we are removing) used to create these dicts.
        # Now, we extract them from our Move objects.
        for item in layer_items_for_viewer:
            if isinstance(item, Move):
                moves_for_viewer_dicts.append(item.to_dict())
            # String items (non-moves) are not directly passed as a separate list to current viewer,
            # but their effect is included if the viewer reconstructs paths from the full item list.
            # For simplicity, the current viewer primarily visualizes the sequence of X,Y,Z from moves.

        actual_layer_display_number = gcode_layer_obj.layer_index_in_document # The "Layer N" from parsing for display title

        if self.viewer_dialog is None:
            self.viewer_dialog = Layer3DViewerDialog(
                mainwin=self,
                layer_idx_in_doc=doc_layer_idx,
                actual_layer_display_number=actual_layer_display_number,
                initial_layer_items=list(layer_items_for_viewer) # Pass the full current items list
            )
        else:
            self.viewer_dialog.set_layer_data(
                layer_idx_in_doc=doc_layer_idx,
                actual_layer_display_number=actual_layer_display_number,
                initial_layer_items=list(layer_items_for_viewer)
            )

        self.viewer_dialog.show()
        self.viewer_dialog.raise_()
        self.viewer_dialog.activateWindow()

    def record_layer_edits(self, layer_idx_in_doc, edited_items_list_from_viewer):
        """
        Called by Layer3DViewerDialog to save its edited items list back to the main window.
        `layer_idx_in_doc` is the index in `self.gcode_document.layers`.
        `edited_items_list_from_viewer` is the list of items (Move objects or strings) from the viewer.
        """
        self.pending_layer_item_edits[layer_idx_in_doc] = edited_items_list_from_viewer

        display_layer_num = -1
        if self.gcode_document and 0 <= layer_idx_in_doc < self.gcode_document.layer_count:
            display_layer_num = self.gcode_document.layers[layer_idx_in_doc].layer_index_in_document

        self.status_bar.showMessage(f"Edits for Layer {display_layer_num} (Doc idx: {layer_idx_in_doc}) recorded. Save document to make permanent.")

    # remove_all_thumbnails - moved to GCodeParser
    # parse_layers - logic moved to GCodeParser.parse_document_to_layers
    # moves_to_gcode - logic moved to GCodeParser.gcode_layer_to_lines
    # save_gcode_file (old) - logic moved to save_gcode_file_action and GCodeFileHandler
    # view_selected_layer (old) - logic moved to view_selected_layer_action
    # save_layer_edits (old) - replaced by record_layer_edits
    # move_index_to_gcode_line - This was specific to old Layer3DViewer's internal G-code line mapping.
    #                          If needed, similar logic might exist in parser or viewer based on item indices.

class LayerSelectorDialog(QDialog): # Mostly unchanged
    def __init__(self, layer_labels, initially_selected_doc_indices, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Layers")
        self.setMinimumWidth(300) # Can be wider if labels are long
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection) # Allow multi-select

        for idx, label in enumerate(layer_labels): # idx here is the index in the list_widget
            self.list_widget.addItem(label)
            # `initially_selected_doc_indices` are indices for `document.layers`
            # The `layer_labels` are generated in order of `document.layers`, so indices match.
            if idx in initially_selected_doc_indices:
                self.list_widget.item(idx).setSelected(True)

        layout.addWidget(self.list_widget)
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(ok_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def get_selected_layers(self):
        # Returns a set of indices corresponding to items in document.layers
        return set([self.list_widget.row(item) for item in self.list_widget.selectedItems()])


class Layer3DViewerDialog(QDialog):
    # `layer_lines` and `moves_override` are replaced by `initial_layer_items`
    def __init__(self, initial_layer_items=None, mainwin=None,
                 layer_idx_in_doc=None, actual_layer_display_number=None, parent=None):
        super().__init__(parent)
        self.mainwin = mainwin
        self.layer_idx_in_doc = layer_idx_in_doc if layer_idx_in_doc is not None else -1
        self.actual_layer_display_number = actual_layer_display_number if actual_layer_display_number is not None else -1

        global viewer_open_count
        viewer_open_count += 1
        self.extruder_head_style = 'sphere' if viewer_open_count == 1 else 'square'

        self.setWindowTitle(f"3D Layer Viewer - Layer {self.actual_layer_display_number} (Doc idx: {self.layer_idx_in_doc})")
        self.setMinimumSize(900, 700)

        # `self.items` will be the working copy of the layer's content (Move objects and strings)
        # It's initialized from `initial_layer_items`. Edits modify this list.
        self.items = list(initial_layer_items) if initial_layer_items else []

        # `self.current_display_moves` is a list of move *dictionaries* derived from `self.items`, for plotting.
        # This needs to be updated whenever `self.items` changes.
        self.current_display_moves = self._get_move_dicts_from_items()

        self.edit_sessions = []
        self.session_colors = [
            (1,0,0,1), (1,0.5,0,1), (1,1,0,1), (0,1,0,1),
            (0,0,1,1), (0.5,0,1,1), (1,0,1,1), (0,1,1,1),
        ]
        self.editor_active = False
        # Slider now refers to index in `self.current_display_moves`
        self.current_slider_index = len(self.current_display_moves) if self.current_display_moves else 0

        self.init_ui_elements() # Renamed from init_ui to avoid conflict
        self.update_plot_and_slider_status() # Renamed

    def _get_move_dicts_from_items(self):
        """Extracts move dictionaries from self.items for visualization."""
        move_dicts = []
        for item in self.items:
            if isinstance(item, Move):
                move_dicts.append(item.to_dict())
        return move_dicts

    def init_ui_elements(self): # Was init_ui
        layout = QVBoxLayout(self)
        self.gl_widget = gl.GLViewWidget()
        self.gl_widget.setBackgroundColor('w')
        layout.addWidget(self.gl_widget, stretch=1)

        top_bar = QHBoxLayout()
        top_bar.addStretch(1)
        self.editor_button = QPushButton("Enable Toolpath Editor")
        self.editor_button.setFixedWidth(270)
        self.editor_button.setFixedHeight(38)
        self.editor_button.clicked.connect(self.toggle_editor_mode)
        top_bar.addWidget(self.editor_button)
        layout.addLayout(top_bar)

        self.dpad_widget = QWidget()
        dpad_layout = QGridLayout()
        dpad_layout.setContentsMargins(0,0,0,0)
        dpad_layout.setSpacing(2)
        self.dpad_buttons = {}
        directions = {
            (0,1): ("▲", "up"),
            (1,2): ("▶", "right"),
            (2,1): ("▼", "down"),
            (1,0): ("◀", "left"),
            (0,0): ("↖", "up_left"),
            (0,2): ("↗", "up_right"),
            (2,0): ("↙", "down_left"),
            (2,2): ("↘", "down_right"),
            (1,1): ("●", None),
        }
        # Map each D-pad button to the requested movement direction:
        # up: -Y, down: +Y, left: +X, right: -X, and fix diagonals accordingly
        for (row, col), (label, direction) in directions.items():
            btn = QPushButton(label)
            btn.setFixedSize(32,32)
            if direction:
                if direction in ["up", "down", "left", "right"]:
                    # Custom grid positions for the intended movement
                    grid_map = {
                        "up": (2,1),      # up (negative Y)
                        "down": (0,1),    # down (positive Y)
                        "left": (1,2),    # left (positive X)
                        "right": (1,0),   # right (negative X)
                    }
                    btn.clicked.connect(lambda checked, g=grid_map[direction]: self.handle_dpad_move_grid(g))
                else:
                    # Diagonal mapping: combine the correct signs for X and Y
                    diag_map = {
                        "up_left": (2,2),      # (+X, -Y)
                        "up_right": (2,0),     # (-X, -Y)
                        "down_left": (0,2),    # (+X, +Y)
                        "down_right": (0,0),   # (-X, +Y)
                    }
                    btn.clicked.connect(lambda checked, g=diag_map[direction]: self.handle_dpad_move_grid(g))
            self.dpad_buttons[direction] = btn
            dpad_layout.addWidget(btn, row, col)
        self.dpad_widget.setLayout(dpad_layout)
        self.dpad_widget.setVisible(False)

        dpad_bar = QHBoxLayout()
        dpad_bar.addStretch(1)
        dpad_bar.addWidget(self.dpad_widget)
        layout.addLayout(dpad_bar)

        slider_layout = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        # Max is based on number of moves derived from items
        self.slider.setMaximum(len(self.current_display_moves) if self.current_display_moves else 1)
        self.slider.setValue(self.current_slider_index if self.current_slider_index > 0 else 1)
        self.slider.valueChanged.connect(self.slider_value_changed_action) # Renamed
        slider_layout.addWidget(self.slider)
        self.status_label = QLabel()
        slider_layout.addWidget(self.status_label)
        self._add_slider_arrows_to_layout(slider_layout)
        layout.addLayout(slider_layout)

        minmax_bar = QHBoxLayout()
        minmax_bar.addStretch(1)
        self.minmax_button = QPushButton("Minimize/Maximize")
        self.minmax_button.setFixedWidth(220)
        self.minmax_button.clicked.connect(self.execute_toggle_minmax_size) # Renamed
        minmax_bar.addWidget(self.minmax_button)
        layout.insertLayout(0, minmax_bar)

        save_bar = QHBoxLayout()
        save_bar.addStretch(1)
        self.apply_edits_button = QPushButton("Apply Edits to Main Window") # Renamed from save_edits_button
        self.apply_edits_button.setFixedWidth(260)
        self.apply_edits_button.clicked.connect(self.trigger_apply_edits_to_mainwin) # Renamed
        save_bar.addWidget(self.apply_edits_button)
        layout.insertLayout(1, save_bar)

        self._is_custom_maximized = False
        self._has_been_shown = False
        # self.update_plot_and_slider_status() # Called from constructor after init_ui_elements

    def _add_slider_arrows_to_layout(self, q_hbox_layout): # Type hint for clarity
        arrow_back = QPushButton('◀')
        arrow_back.setFixedWidth(32)
        arrow_forward = QPushButton('▶')
        arrow_forward.setFixedWidth(32)
        arrow_back.clicked.connect(self.step_slider_backward_action) # Renamed
        arrow_forward.clicked.connect(self.step_slider_forward_action) # Renamed
        q_hbox_layout.insertWidget(0, arrow_back)
        q_hbox_layout.addWidget(arrow_forward)
        # self.arrow_back = arrow_back # Not strictly needed if only connected
        # self.arrow_forward = arrow_forward

    # Replaces original set_layer and parts of __init__
    def set_layer_data(self, layer_idx_in_doc=None, actual_layer_display_number=None, initial_layer_items=None):

        self.layer_idx_in_doc = layer_idx_in_doc if layer_idx_in_doc is not None else self.layer_idx_in_doc
        self.actual_layer_display_number = actual_layer_display_number if actual_layer_display_number is not None else self.actual_layer_display_number

        self.items = list(initial_layer_items) if initial_layer_items is not None else []
        self.current_display_moves = self._get_move_dicts_from_items()

        self.setWindowTitle(f"3D Layer Viewer - Layer {self.actual_layer_display_number} (Doc idx: {self.layer_idx_in_doc})")

        num_moves = len(self.current_display_moves)
        self.current_slider_index = num_moves if num_moves > 0 else 0 # Slider position (1-based for UI if num_moves > 0)
        self.slider.setMaximum(num_moves if num_moves > 0 else 1)
        self.slider.setValue(self.current_slider_index if self.current_slider_index > 0 else 1)

        self.edit_sessions = []
        self.editor_active = False
        self.dpad_widget.setVisible(False)
        self.editor_button.setText("Enable Toolpath Editor")
        self.editor_button.setStyleSheet("")

        self.update_plot_and_slider_status()

    # Original parse_moves is removed, as items/moves are now passed in.

    def slider_value_changed_action(self, value):
        self.current_slider_index = value
        self.update_plot_and_slider_status()

    def update_plot_and_slider_status(self): # Was update_plot
        self.gl_widget.clear()

        num_render_points = self.current_slider_index # This is 1-based from slider, meaning number of points to consider

        if not self.current_display_moves or num_render_points == 0:
            self.status_label.setText("No moves to display.")
            # Setup camera for empty grid if needed
            # self._setup_camera_for_plot(np.array([]))
            return

        # Filter out moves with None for x, y, or z
        filtered_moves = [m for m in self.current_display_moves[:num_render_points] if m['x'] is not None and m['y'] is not None and m['z'] is not None]
        if not filtered_moves:
            self.status_label.setText("No valid moves to display.")
            return

        points_to_render_np = np.array([[m['x'], m['y'], m['z']] for m in filtered_moves])

        grid = gl.GLGridItem()
        # Dynamic grid sizing based on all points in the layer for consistent view
        all_points_for_grid = np.array([[m['x'], m['y'], m['z']] for m in self.current_display_moves if m['x'] is not None and m['y'] is not None and m['z'] is not None])
        if all_points_for_grid.size >0:
            x_span = np.ptp(all_points_for_grid[:,0]) if all_points_for_grid.shape[0] > 0 else 100
            y_span = np.ptp(all_points_for_grid[:,1]) if all_points_for_grid.shape[0] > 0 else 100
            grid_size = max(x_span, y_span, 20) # Ensure grid is at least 20x20
            grid.setSize(x=grid_size, y=grid_size)
            grid.setSpacing(x=grid_size/10, y=grid_size/10) # 10 grid lines
            # Center grid based on all points
            center_x = np.mean(all_points_for_grid[:,0]) if all_points_for_grid.shape[0] > 0 else 0
            center_y = np.mean(all_points_for_grid[:,1]) if all_points_for_grid.shape[0] > 0 else 0
            grid.translate(center_x, center_y, 0) # Assuming Z=0 for grid plane
        self.gl_widget.addItem(grid)

        # Draw toolpath segments. A segment exists from point i-1 to point i.
        # This segment corresponds to the properties of move i (the end point of the segment).
        for i in range(1, len(filtered_moves)):
            segment_coords_np = np.array([points_to_render_np[i-1], points_to_render_np[i]])
            move_properties_dict = filtered_moves[i]

            color, width, antialias, is_dotted = self._get_segment_style_from_move(move_properties_dict)

            if is_dotted:
                # Create dotted line effect (simplified)
                num_dots = 10
                for j in range(0, num_dots -1, 2): # Draw every other segment
                    start_frac = j / num_dots
                    end_frac = (j+1) / num_dots
                    dot_start_pt = segment_coords_np[0] + (segment_coords_np[1] - segment_coords_np[0]) * start_frac
                    dot_end_pt = segment_coords_np[0] + (segment_coords_np[1] - segment_coords_np[0]) * end_frac
                    dot_line_item = gl.GLLinePlotItem(pos=np.array([dot_start_pt, dot_end_pt]),
                                                      color=color, width=width, antialias=antialias, mode='lines')
                    dot_line_item.setGLOptions('translucent')
                    self.gl_widget.addItem(dot_line_item)
            else:
                line_item = gl.GLLinePlotItem(pos=segment_coords_np, color=color, width=width, antialias=antialias, mode='lines')
                self.gl_widget.addItem(line_item)

        # Draw edit session lines (if editor active and sessions exist)
        if self.editor_active and self.edit_sessions:
            for session in self.edit_sessions:
                # `origin_move_idx_in_items` and `current_tip_move_idx_in_items` refer to indices in `self.items`
                # We need to map these to `self.current_display_moves` or use stored coordinates.
                # Session stores `origin_coords_np` and `current_tip_coords_np`.
                if session.get('origin_coords_np') is not None and session.get('current_tip_coords_np') is not None:
                    origin_np = session['origin_coords_np']
                    current_tip_np = session['current_tip_coords_np']
                    if not np.allclose(origin_np, current_tip_np):
                        seg_np = np.array([origin_np, current_tip_np])
                        edit_line = gl.GLLinePlotItem(pos=seg_np, color=session['color'], width=7, antialias=True, mode='lines')
                        self.gl_widget.addItem(edit_line)

        # Draw extruder head at the current position (the last point in points_to_render_np)
        if len(points_to_render_np) > 0:
            extruder_pos_np = points_to_render_np[-1]  # Use last valid point, not num_render_points-1
            self._draw_extruder_head_at(extruder_pos_np)

        self.status_label.setText(f"Move {len(filtered_moves)} / {len(self.current_display_moves)}")

        # Setup camera based on all points in the layer for consistent framing
        if all_points_for_grid.size > 0:
            self._setup_camera_for_plot(all_points_for_grid)
        self.gl_widget.setBackgroundColor('w')


    def _get_segment_style_from_move(self, move_dict):
        move_type = move_dict.get('type')
        color = (0.5, 0.5, 0.5, 1)  # Default: gray
        width = 3; antialias = True; is_dotted = False

        if move_type == 'external_perimeter': color = (0.5, 0, 0.5, 1)  # Purple
        elif move_type == 'perimeter': color = (0, 0, 1, 1)  # Blue
        elif move_type == 'travel':
            color = (0, 1, 0, 1); width = 2; antialias = False; is_dotted = True
        return color, width, antialias, is_dotted

    def _draw_extruder_head_at(self, position_np):
        style = self.extruder_head_style
        if style == 'sphere':
            try:
                mesh_data = gl.MeshData.sphere(rows=10, cols=10, radius=0.625)
                head_item = gl.GLMeshItem(meshdata=mesh_data, color=(1,0,0,1), smooth=True, shader='balloon', drawEdges=False)
                head_item.translate(position_np[0], position_np[1], position_np[2])
                head_item.setGLOptions('opaque')
                self.gl_widget.addItem(head_item)
            except Exception: # Fallback
                style = 'square' # Force fallback to scatter plot
        if style == 'square': # Fallback or chosen style
            scatter_item = gl.GLScatterPlotItem(pos=np.array([position_np]), color=(1,0,0,1), size=15, pxMode=True)
            scatter_item.setGLOptions('opaque')
            self.gl_widget.addItem(scatter_item)

    def _setup_camera_for_plot(self, points_np_array): # Was _setup_camera
        if points_np_array.shape[0] == 0:
            # Default camera for empty plot
            self.gl_widget.setCameraPosition(distance=100, elevation=90, azimuth=0)  # Top-down
            return

        min_coords = points_np_array.min(axis=0)
        max_coords = points_np_array.max(axis=0)
        center_coords = (min_coords + max_coords) / 2
        center_vec = pg.Vector(center_coords[0], center_coords[1], center_coords[2])

        obj_span = max_coords - min_coords
        distance = max(obj_span[0], obj_span[1], obj_span[2], 20) * 1.5 # Ensure object fits, min distance 20*1.5

        # Always use top-down view: elevation=90, azimuth=0
        self.gl_widget.setCameraPosition(pos=center_vec, distance=distance, elevation=90, azimuth=0)

    def step_slider_backward_action(self): # Was slider_back
        val = self.slider.value()
        if val > self.slider.minimum():
            self.slider.setValue(val - 1)

    def step_slider_forward_action(self): # Was slider_forward
        val = self.slider.value()
        if val < self.slider.maximum():
            self.slider.setValue(val + 1)

    def toggle_editor_mode(self): # Was toggle_editor
        if not self.dpad_widget.isVisible(): # To enable editor
            if not self.current_display_moves:
                QMessageBox.warning(self, "Cannot Edit", "No moves loaded to edit.")
                return

            # Determine the item index in self.items corresponding to current slider position
            # Slider index is 1-based for current_display_moves.
            # current_display_moves[slider_idx - 1] is the target move dict.
            # We need to find this Move object in self.items.

            current_move_dict_idx = self.current_slider_index -1
            if not (0 <= current_move_dict_idx < len(self.current_display_moves)):
                QMessageBox.warning(self, "Error", "Slider position invalid for starting edit.")
                return

            target_move_dict = self.current_display_moves[current_move_dict_idx]

            # Find the corresponding Move object in self.items
            # This is tricky if Move objects don't have unique IDs. Assume sequence for now.
            # A more robust way: store (item_index, move_dict_index) map or search by coords.
            # Simplified: assume current_move_dict_idx maps to the Nth Move object in self.items
            count_moves_in_items = 0
            origin_item_idx = -1 # Index in self.items of the Move object we are starting from
            for i, item in enumerate(self.items):
                if isinstance(item, Move):
                    if count_moves_in_items == current_move_dict_idx:
                        origin_item_idx = i
                        break
                    count_moves_in_items +=1

            if origin_item_idx == -1:
                QMessageBox.critical(self, "Error", "Could not find starting move in internal items list.")
                return

            self.dpad_widget.setVisible(True)
            self.editor_button.setText("Stop Editing Session")
            self.editor_button.setStyleSheet("background-color: red; color: white;")
            self.editor_active = True

            start_move_obj = self.items[origin_item_idx] # Should be a Move object
            start_coords_np = np.array([start_move_obj.x, start_move_obj.y, start_move_obj.z])

            session_color = self.session_colors[len(self.edit_sessions) % len(self.session_colors)]
            new_session = {
                'origin_item_idx_in_items': origin_item_idx, # Index in self.items of the Move we started from
                'current_tip_item_idx_in_items': origin_item_idx, # Index in self.items of the current tip of this session's edits
                'origin_coords_np': start_coords_np,
                'current_tip_coords_np': np.copy(start_coords_np), # Initially tip is at origin
                'color': session_color,
                'dpad_deltas_this_session': [], # Store (dx,dy) of D-pad moves in this session
            }
            self.edit_sessions.append(new_session)
        else: # To disable editor
            self.dpad_widget.setVisible(False)
            self.editor_button.setText("Enable Toolpath Editor")
            self.editor_button.setStyleSheet("")
            self.editor_active = False
            # Finalize path patching if any complex logic was needed (e.g., connect back to next original move)
            # For now, edits are directly inserted into self.items.

        self.update_plot_and_slider_status()


    def handle_dpad_move(self, direction_key):
        # Only used for fallback/diagonals
        if not self.editor_active or not self.edit_sessions or not self.items:
            return
        current_session = self.edit_sessions[-1]
        idx_of_item_to_insert_after = current_session['current_tip_item_idx_in_items']
        if not (0 <= idx_of_item_to_insert_after < len(self.items)): return
        last_coords_np = current_session['current_tip_coords_np']
        last_e_value = 0.0 # Default E
        if isinstance(self.items[idx_of_item_to_insert_after], Move):
            last_e_value = self.items[idx_of_item_to_insert_after].e or 0.0
        d = 2.0
        d_diag = d * (2 ** 0.5) / 2
        # Only fallback for diagonals
        dir_vectors_xy = {
            "up_right": np.array([d_diag, -d_diag]),
            "up_left": np.array([d_diag, d_diag]),
            "down_right": np.array([-d_diag, -d_diag]),
            "down_left": np.array([-d_diag, d_diag]),
        }
        delta_xy = dir_vectors_xy.get(direction_key)
        if delta_xy is None:
            return
        # Basic undo: if move is opposite to last dpad delta in session
        if current_session['dpad_deltas_this_session']:
            last_delta = current_session['dpad_deltas_this_session'][-1]
            if np.allclose(delta_xy, -last_delta):
                if 0 <= idx_of_item_to_insert_after < len(self.items) and \
                   isinstance(self.items[idx_of_item_to_insert_after], Move) and \
                   self.items[idx_of_item_to_insert_after].type == 'travel_edit':
                    self.items.pop(idx_of_item_to_insert_after)
                    current_session['dpad_deltas_this_session'].pop()
                    current_session['current_tip_item_idx_in_items'] = idx_of_item_to_insert_after -1
                    if isinstance(self.items[current_session['current_tip_item_idx_in_items']], Move):
                        prev_move_obj = self.items[current_session['current_tip_item_idx_in_items']]
                        current_session['current_tip_coords_np'] = np.array([prev_move_obj.x, prev_move_obj.y, prev_move_obj.z])
                    self.current_display_moves = self._get_move_dicts_from_items()
                    self.slider.setMaximum(len(self.current_display_moves) if self.current_display_moves else 1)
                    if self.slider.value() > 1 : self.slider.setValue(self.slider.value() -1)
                    self.update_plot_and_slider_status()
                    return
        new_x = last_coords_np[0] + delta_xy[0]
        new_y = last_coords_np[1] + delta_xy[1]
        lift_height = 1.0
        new_z = last_coords_np[2] + lift_height
        new_move_obj = Move(x=new_x, y=new_y, z=new_z, e=last_e_value, move_type='travel_edit', original_line_index=None)
        insert_at_item_idx = idx_of_item_to_insert_after + 1
        self.items.insert(insert_at_item_idx, new_move_obj)
        current_session['dpad_deltas_this_session'].append(delta_xy)
        current_session['current_tip_item_idx_in_items'] = insert_at_item_idx
        current_session['current_tip_coords_np'] = np.array([new_x, new_y, new_z])
        self.current_display_moves = self._get_move_dicts_from_items()
        self.slider.setMaximum(len(self.current_display_moves) if self.current_display_moves else 1)
        newly_inserted_move_display_idx = -1
        move_count = 0
        for item_idx, item_val in enumerate(self.items):
            if item_val is new_move_obj:
                newly_inserted_move_display_idx = move_count
                break
            if isinstance(item_val, Move):
                move_count += 1
        if newly_inserted_move_display_idx != -1:
            self.slider.setValue(newly_inserted_move_display_idx + 1)
        else:
            if self.slider.value() < self.slider.maximum(): self.slider.setValue(self.slider.value()+1)
        self.update_plot_and_slider_status()

    def handle_dpad_move_grid(self, grid_pos):
        # Map grid_pos to movement vector
        d = 2.0
        d_diag = d * (2 ** 0.5) / 2
        grid_to_delta = {
            (1,0): np.array([0, d]),      # up
            (1,2): np.array([0, -d]),     # down
            (0,1): np.array([d, 0]),      # right
            (2,1): np.array([-d, 0]),     # left
            (0,0): np.array([d_diag, d_diag]),      # up_left
            (0,2): np.array([d_diag, -d_diag]),     # up_right
            (2,0): np.array([-d_diag, d_diag]),     # down_left
            (2,2): np.array([-d_diag, -d_diag]),    # down_right
        }
        direction_key = None # Not used in this handler
        delta_xy = grid_to_delta.get(grid_pos)
        if delta_xy is None:
            return
        # The rest of this function is the same as handle_dpad_move, but uses delta_xy
        if not self.editor_active or not self.edit_sessions or not self.items:
            return
        current_session = self.edit_sessions[-1]
        idx_of_item_to_insert_after = current_session['current_tip_item_idx_in_items']
        if not (0 <= idx_of_item_to_insert_after < len(self.items)): return
        last_coords_np = current_session['current_tip_coords_np']
        last_e_value = 0.0 # Default E
        if isinstance(self.items[idx_of_item_to_insert_after], Move):
            last_e_value = self.items[idx_of_item_to_insert_after].e or 0.0
        # Basic undo: if move is opposite to last dpad delta in session
        if current_session['dpad_deltas_this_session']:
            last_delta = current_session['dpad_deltas_this_session'][-1]
            if np.allclose(delta_xy, -last_delta):
                if 0 <= idx_of_item_to_insert_after < len(self.items) and \
                   isinstance(self.items[idx_of_item_to_insert_after], Move) and \
                   self.items[idx_of_item_to_insert_after].type == 'travel_edit':
                    self.items.pop(idx_of_item_to_insert_after)
                    current_session['dpad_deltas_this_session'].pop()
                    current_session['current_tip_item_idx_in_items'] = idx_of_item_to_insert_after -1
                    if isinstance(self.items[current_session['current_tip_item_idx_in_items']], Move):
                        prev_move_obj = self.items[current_session['current_tip_item_idx_in_items']]
                        current_session['current_tip_coords_np'] = np.array([prev_move_obj.x, prev_move_obj.y, prev_move_obj.z])
                    self.current_display_moves = self._get_move_dicts_from_items()
                    self.slider.setMaximum(len(self.current_display_moves) if self.current_display_moves else 1)
                    if self.slider.value() > 1 : self.slider.setValue(self.slider.value() -1)
                    self.update_plot_and_slider_status()
                    return
        new_x = last_coords_np[0] + delta_xy[0]
        new_y = last_coords_np[1] + delta_xy[1]
        lift_height = 1.0
        new_z = last_coords_np[2] + lift_height
        new_move_obj = Move(x=new_x, y=new_y, z=new_z, e=last_e_value, move_type='travel_edit', original_line_index=None)
        insert_at_item_idx = idx_of_item_to_insert_after + 1
        self.items.insert(insert_at_item_idx, new_move_obj)
        current_session['dpad_deltas_this_session'].append(delta_xy)
        current_session['current_tip_item_idx_in_items'] = insert_at_item_idx
        current_session['current_tip_coords_np'] = np.array([new_x, new_y, new_z])
        self.current_display_moves = self._get_move_dicts_from_items()
        self.slider.setMaximum(len(self.current_display_moves) if self.current_display_moves else 1)
        newly_inserted_move_display_idx = -1
        move_count = 0
        for item_idx, item_val in enumerate(self.items):
            if item_val is new_move_obj:
                newly_inserted_move_display_idx = move_count
                break
            if isinstance(item_val, Move):
                move_count += 1
        if newly_inserted_move_display_idx != -1:
            self.slider.setValue(newly_inserted_move_display_idx + 1)
        else:
            if self.slider.value() < self.slider.maximum(): self.slider.setValue(self.slider.value()+1)
        self.update_plot_and_slider_status()

    def trigger_apply_edits_to_mainwin(self): # Was save_edits
        if self.mainwin and hasattr(self.mainwin, 'record_layer_edits'):
            # Pass the current state of self.items (which includes Move objects and strings)
            self.mainwin.record_layer_edits(self.layer_idx_in_doc, list(self.items)) # Pass a copy
            QMessageBox.information(self, "Edits Applied", f"Edits for layer {self.actual_layer_display_number} sent to main window. Save the document to make them permanent.")
        else:
            QMessageBox.warning(self, "Error", "Cannot apply edits: Main window link is broken.")


    def showEvent(self, event):
        if not self._has_been_shown:
            screen_geom = QApplication.primaryScreen().availableGeometry()
            default_w, default_h = int(screen_geom.width()*0.35), int(screen_geom.height()*0.35)
            self.resize(default_w, default_h)
            self.move((screen_geom.width()-default_w)//2, (screen_geom.height()-default_h)//2)
            self._is_custom_maximized = False
            self._has_been_shown = True
        super().showEvent(event)

    def execute_toggle_minmax_size(self): # Was toggle_minmax
        screen_geom = QApplication.primaryScreen().availableGeometry()
        min_w, min_h = int(screen_geom.width()*0.35), int(screen_geom.height()*0.35)
        max_w, max_h = int(screen_geom.width()*0.90), int(screen_geom.height()*0.90)

        if not self._is_custom_maximized :
            self.resize(max_w, max_h)
            self.move((screen_geom.width()-max_w)//2, (screen_geom.height()-max_h)//2)
            self._is_custom_maximized = True
        else:
            self.resize(min_w, min_h)
            self.move((screen_geom.width()-min_w)//2, (screen_geom.height()-min_h)//2)
            self._is_custom_maximized = False

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    # move_index_to_gcode_line - Removed. Mapping is now based on self.items and its relation to self.current_display_moves.
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GCodeEditor()
    window.show()
    sys.exit(app.exec_())
