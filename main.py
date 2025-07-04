@ -1,845 +0,0 @@
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QStatusBar, QLabel,
    QListWidget, QAbstractItemView, QHBoxLayout, QDialog, QPushButton, QSlider, QGridLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import os
import pyqtgraph.opengl as gl
import pyqtgraph as pg
import numpy as np

viewer_open_count = 0

class GCodeEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Printing Toolpath (G-code) Editor")
        self.setGeometry(100, 100, 650, 350)
        self.gcode_file_path = None
        self.cleaned_gcode = None
        self.layer_indices = []
        self.layer_labels = []
        self.selected_layers = set()
        self.viewer_dialog = None  # Persistent 3D viewer dialog
        self.layer_edits = {}  # Store edits per layer index
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
        self.open_button.clicked.connect(self.open_gcode_file)
        btn_layout.addWidget(self.open_button)

        self.save_button = QPushButton("Save As")
        self.save_button.setMinimumHeight(32)
        self.save_button.setFont(QFont('Arial', 11))
        self.save_button.clicked.connect(self.save_gcode_file)
        self.save_button.setEnabled(False)
        btn_layout.addWidget(self.save_button)

        self.layer_button = QPushButton("Select Layers")
        self.layer_button.setMinimumHeight(32)
        self.layer_button.setFont(QFont('Arial', 11))
        self.layer_button.clicked.connect(self.show_layer_selector)
        self.layer_button.setEnabled(False)
        btn_layout.addWidget(self.layer_button)

        self.view_layer_button = QPushButton("View Layer 3D")
        self.view_layer_button.setMinimumHeight(32)
        self.view_layer_button.setFont(QFont('Arial', 11))
        self.view_layer_button.clicked.connect(self.view_selected_layer)
        self.view_layer_button.setEnabled(False)
        btn_layout.addWidget(self.view_layer_button)

        main_layout.addLayout(btn_layout)

        # Placeholder for 3D G-code viewer
        # TODO: Add 3D viewer widget here in the future

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def open_gcode_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select G-code File", "", "G-code Files (*.gcode *.nc *.txt);;All Files (*)")
        if file_path:
            self.gcode_file_path = file_path
            filename = os.path.basename(file_path)
            self.info_label.setText(f"Selected: {filename}")
            self.save_button.setEnabled(True)
            self.status_bar.showMessage(f"Selected: {filename}")
            try:
                with open(file_path, 'r') as file:
                    gcode = file.readlines()
                self.cleaned_gcode = self.remove_all_thumbnails(gcode)
                self.parse_layers(self.cleaned_gcode)
                self.layer_button.setEnabled(True if self.layer_indices else False)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to read file: {e}")
                self.cleaned_gcode = None
                self.layer_indices = []
                self.layer_labels = []
                self.layer_button.setEnabled(False)
        else:
            self.status_bar.showMessage("No file selected.")

    def parse_layers(self, lines):
        self.layer_indices = []
        self.layer_labels = []
        for i, line in enumerate(lines):
            if line.strip() == ';LAYER_CHANGE':
                label = f"Layer {len(self.layer_indices)}"
                self.layer_indices.append(i)
                self.layer_labels.append(label)

    def show_layer_selector(self):
        if not self.layer_labels:
            QMessageBox.warning(self, "Warning", "No layers found in the G-code file.")
            return
        dlg = LayerSelectorDialog(self.layer_labels, self.selected_layers, self)
        if dlg.exec_():
            self.selected_layers = dlg.get_selected_layers()
            if not self.selected_layers:
                QMessageBox.warning(self, "Warning", "No layers selected.")
                self.view_layer_button.setEnabled(False)
            elif len(self.selected_layers) == 1:
                self.view_layer_button.setEnabled(True)
                self.status_bar.showMessage(f"Selected layer: {list(self.selected_layers)[0]}")
            else:
                self.view_layer_button.setEnabled(False)
                self.status_bar.showMessage(f"Selected layers: {sorted(self.selected_layers)}")

    def remove_all_thumbnails(self, lines):
        cleaned = []
        skip = False
        for line in lines:
            if 'thumbnail_QOI begin' in line or 'thumbnail begin' in line:
                skip = True
                continue
            if 'thumbnail_QOI end' in line or 'thumbnail end' in line:
                skip = False
                continue
            if not skip:
                cleaned.append(line)
        return cleaned

    def moves_to_gcode(self, moves):
        # Convert moves (list of dicts) back to G-code lines
        gcode_lines = []
        last_e_val_in_gcode = None # Tracks the E value actually written in the last G-code line that had an E.

        for m in moves:
            x_str = f"X{m['x']:.3f}" if 'x' in m and m['x'] is not None else ''
            y_str = f"Y{m['y']:.3f}" if 'y' in m and m['y'] is not None else ''
            z_str = f"Z{m['z']:.3f}" if 'z' in m and m['z'] is not None else ''
            e_str = '' # Default to no E parameter

            if m.get('type') == 'travel':
                # For travel moves, no E parameter is written.
                # The extruder holds its position from the last extrusion.
                # The m['e'] in the move dictionary should still reflect this logical extruder position.
                pass # e_str remains empty, so no E parameter will be added to the G-code line.
            else: # Non-travel (presumably extrusion)
                if 'e' in m and m['e'] is not None:
                    current_move_e_val = m['e']
                    # Write E only if it's different from the last written E value, 
                    # or if no E has been written yet in this sequence of moves.
                    if last_e_val_in_gcode is None or abs(current_move_e_val - last_e_val_in_gcode) > 1e-5: # Use 1e-5 for float comparison
                        e_str = f"E{current_move_e_val:.5f}"
                        # Update last_e_val_in_gcode because we are deciding to write this E value.
                        last_e_val_in_gcode = current_move_e_val
                    # If E is same as last written, e_str remains empty (no redundant E parameter)
                # If a non-travel move has no 'e' in its dictionary (e.g., a G1 Z-only move), 
                # e_str remains empty, which is correct.

            # Add type comments before the G-code line
            # These comments help identify the purpose of the following G-code move.
            if m.get('type') == 'external_perimeter':
                gcode_lines.append(';TYPE:External perimeter\n')
            elif m.get('type') == 'perimeter':
                gcode_lines.append(';TYPE:Perimeter\n')
            # Not adding ;TYPE:Travel as it's usually implicit by lack of E or specific G0 command (though we use G1 for all moves).
            # Other types like 'None' will not have a comment.

            # Construct the G-code line.
            # All moves are currently written as G1, as per the original code's behavior.
            gline_parts = ["G1"]
            if x_str: gline_parts.append(x_str)
            if y_str: gline_parts.append(y_str)
            if z_str: gline_parts.append(z_str)
            if e_str: gline_parts.append(e_str)
            
            gline = " ".join(gline_parts)

            # Only add the line if it's more than just "G1" (i.e., it has parameters).
            # A "G1" line by itself is invalid.
            if len(gline_parts) > 1:
                gcode_lines.append(gline + '\n')
            # If the line was just "G1" but it was supposed to be an E-only move where E didn't change,
            # it's correctly omitted. If it was a travel move with no X,Y,Z change, it's also omitted.

        return gcode_lines

    def save_gcode_file(self):
        if not self.gcode_file_path or self.cleaned_gcode is None:
            QMessageBox.warning(self, "Warning", "No G-code file loaded or cleaned G-code is missing.")
            return
        if not self.selected_layers:
            QMessageBox.warning(self, "Warning", "No layers selected for editing.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save G-code File As", "", "G-code Files (*.gcode *.nc *.txt);;All Files (*)")
        if file_path:
            try:
                # Build new G-code with edits, inserting at correct positions
                new_gcode = []
                layer_ptrs = self.layer_indices + [len(self.cleaned_gcode)]
                for i, (start, end) in enumerate(zip(layer_ptrs[:-1], layer_ptrs[1:])):
                    # Always add ;LAYER_CHANGE at the start of each saved layer
                    if self.cleaned_gcode[start].strip() != ';LAYER_CHANGE':
                        new_gcode.append(';LAYER_CHANGE\n')
                    else:
                        new_gcode.append(self.cleaned_gcode[start])
                    if i in self.layer_edits:
                        orig_lines = list(self.cleaned_gcode[start+1:end])  # skip the original ;LAYER_CHANGE
                        # 1. Parse all moves and collect non-move lines with their indices
                        moves = []
                        non_move_lines = []  # (idx, line)
                        gcode_to_move_idx = {}  # Map G-code line idx -> move idx
                        move_counter = 0
                        for idx, line in enumerate(orig_lines):
                            l = line.strip()
                            if l.startswith(('G0', 'G1', 'G01', 'G2', 'G3')):
                                # Parse move
                                parts = l.split()
                                move = {'type': None, 'x': None, 'y': None, 'z': None, 'e': None}
                                for part in parts:
                                    if part.startswith('X'):
                                        move['x'] = float(part[1:])
                                    elif part.startswith('Y'):
                                        move['y'] = float(part[1:])
                                    elif part.startswith('Z'):
                                        move['z'] = float(part[1:])
                                    elif part.startswith('E'):
                                        move['e'] = float(part[1:])
                                # Try to infer type from previous comment
                                if idx > 0 and orig_lines[idx-1].strip().startswith(';TYPE:'):
                                    move['type'] = orig_lines[idx-1].strip()[6:].lower()
                                moves.append(move)
                                gcode_to_move_idx[idx] = move_counter
                                move_counter += 1
                            else:
                                non_move_lines.append((idx, line))
                        # 2. Apply all edits to the move list (using move dicts from the 3D viewer)
                        edits = self.layer_edits[i]
                        offset = 0
                        for gcode_idx, edit_moves in sorted(edits, key=lambda x: x[0]):
                            # Map G-code line index to move index
                            move_idx = gcode_to_move_idx.get(gcode_idx, None)
                            if move_idx is None:
                                continue  # Skip if not a move line
                            move_idx += offset
                            for m in edit_moves:
                                m['type'] = 'travel'
                            # Replace the move at move_idx with the edited moves
                            moves[move_idx:move_idx+1] = edit_moves
                            # Patch the next move to be a travel move
                            next_idx = move_idx + len(edit_moves)
                            if next_idx < len(moves):
                                patch = dict(edit_moves[-1])
                                patch['x'] = moves[next_idx]['x']
                                patch['y'] = moves[next_idx]['y']
                                patch['z'] = moves[next_idx]['z']
                                patch['type'] = 'travel'
                                patch['e'] = edit_moves[-1]['e']
                                moves[next_idx] = patch
                            offset += len(edit_moves) - 1
                        # 3. Regenerate G-code for the layer from the move list
                        gcode_lines = self.moves_to_gcode(moves)
                        # 4. Re-insert all non-move lines at their original indices
                        for idx, line in non_move_lines:
                            gcode_lines.insert(idx, line)
                        new_gcode.extend(gcode_lines)
                    else:
                        new_gcode.extend(self.cleaned_gcode[start+1:end])
                with open(file_path, 'w') as file:
                    file.writelines(new_gcode)
                self.status_bar.showMessage(f"Saved: {file_path}")
                QMessageBox.information(self, "Saved", f"G-code saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file: {e}")
        else:
            self.status_bar.showMessage("Save operation cancelled.")

    def view_selected_layer(self):
        if len(self.selected_layers) != 1:
            QMessageBox.warning(self, "Warning", "Please select exactly one layer to view.")
            return
        idx = list(self.selected_layers)[0]
        start = self.layer_indices[idx]
        end = self.layer_indices[idx+1] if idx+1 < len(self.layer_indices) else len(self.cleaned_gcode)
        layer_lines = self.cleaned_gcode[start:end]
        moves_override = self.layer_edits.get(idx, None)
        if self.viewer_dialog is None:
            self.viewer_dialog = Layer3DViewerDialog(layer_lines, mainwin=self, layer_idx=idx, moves_override=moves_override)
        else:
            self.viewer_dialog.set_layer(layer_lines, layer_idx=idx, moves_override=moves_override)
        self.viewer_dialog.show()
        self.viewer_dialog.raise_()
        self.viewer_dialog.activateWindow()

    def save_layer_edits(self, layer_idx, moves):
        self.layer_edits[layer_idx] = moves

    def move_index_to_gcode_line(self, move_idx):
        """
        Map a move index (from self.moves) to the corresponding G-code line index in self.layer_lines.
        Returns the G-code line index where the move at move_idx starts.
        """
        move_count = 0
        for i, line in enumerate(self.layer_lines):
            line = line.strip()
            if not line or line.startswith('M'):
                continue
            if line.startswith('G0') or line.startswith('G1') or line.startswith('G01') or line.startswith('G2') or line.startswith('G3'):
                if move_count == move_idx:
                    return i
                move_count += 1
        # If not found, return end of layer
        return len(self.layer_lines)

class LayerSelectorDialog(QDialog):
    def __init__(self, layer_labels, selected_layers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Layers")
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        for idx, label in enumerate(layer_labels):
            self.list_widget.addItem(label)
            if idx in selected_layers:
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
        return set([i.row() for i in self.list_widget.selectedIndexes()])

class Layer3DViewerDialog(QDialog):
    def __init__(self, layer_lines, parent=None, mainwin=None, layer_idx=None, moves_override=None):
        super().__init__(parent)
        self.mainwin = mainwin
        self.layer_idx = layer_idx if layer_idx is not None else -1
        global viewer_open_count
        viewer_open_count += 1
        if viewer_open_count == 1:
            self.extruder_head_style = 'sphere'
        else:
            self.extruder_head_style = 'square'
        self.setWindowTitle("3D Layer Viewer")
        self.setMinimumSize(900, 700)
        self.setWindowState(self.windowState() | Qt.WindowMaximized)
        self.layer_lines = layer_lines
        self.moves = self.parse_moves(layer_lines)
        self.edit_sessions = []  # List of dicts: {'origin_idx', 'current_idx', 'color', 'move_stack', 'origin_coords'}
        self.session_colors = [
            (1,0,0,1),      # Red
            (1,0.5,0,1),    # Orange
            (1,1,0,1),      # Yellow
            (0,1,0,1),      # Green
            (0,0,1,1),      # Blue
            (0.5,0,1,1),    # Purple
            (1,0,1,1),      # Magenta
            (0,1,1,1),      # Cyan
        ]
        self.session_color_idx = 0
        self.manual_origin_idx = None
        self.manual_current_idx = None
        self.manual_move_stack = []
        self.editor_active = False
        self.current_index = len(self.moves) if self.moves else 0
        layout = QVBoxLayout(self)
        self.gl_widget = gl.GLViewWidget()
        self.gl_widget.setBackgroundColor('w')
        layout.addWidget(self.gl_widget, stretch=1)
        # Add Toolpath Editor button and D-pad
        self.editor_button = QPushButton("Enable Toolpath Editor")
        self.editor_button.setFixedWidth(270)  # Even wider for text
        self.editor_button.setFixedHeight(38)
        self.editor_button.clicked.connect(self.toggle_editor)
        # Place in a horizontal layout, right-aligned
        top_bar = QHBoxLayout()
        top_bar.addStretch(1)
        top_bar.addWidget(self.editor_button)
        layout.addLayout(top_bar)
        # D-Pad controls (hidden by default)
        self.dpad_widget = QWidget()
        dpad_layout = QGridLayout()
        dpad_layout.setContentsMargins(0,0,0,0)
        dpad_layout.setSpacing(2)
        self.dpad_buttons = {}
        directions = {
            (0,1): ("▲", "up"),
            (0,2): ("↗", "up_right"),
            (1,0): ("◀", "left"),
            (1,1): ("●", None),
            (1,2): ("▶", "right"),
            (2,0): ("↙", "down_left"),
            (2,1): ("▼", "down"),
            (2,2): ("↘", "down_right"),
            (0,0): ("↖", "up_left"),
        }
        for (row, col), (label, direction) in directions.items():
            btn = QPushButton(label)
            btn.setFixedSize(32,32)
            if direction:
                btn.clicked.connect(lambda checked, d=direction: self.move_extruder(d))
            self.dpad_buttons[direction] = btn
            dpad_layout.addWidget(btn, row, col)
        self.dpad_widget.setLayout(dpad_layout)
        self.dpad_widget.setVisible(False)
        # Place D-pad in a horizontal layout, right-aligned
        dpad_bar = QHBoxLayout()
        dpad_bar.addStretch(1)
        dpad_bar.addWidget(self.dpad_widget)
        layout.addLayout(dpad_bar)
        slider_layout = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(len(self.moves) if self.moves else 1)
        self.slider.setValue(self.current_index)
        self.slider.valueChanged.connect(self.update_plot)
        slider_layout.addWidget(self.slider)
        self.status_label = QLabel()
        slider_layout.addWidget(self.status_label)
        self.add_slider_arrows(slider_layout)
        layout.addLayout(slider_layout)
        self.update_plot()
        # Widen Minimize/Maximize and Save Edits buttons
        self.minmax_button = QPushButton("Minimize/Maximize")
        self.minmax_button.setFixedWidth(220)
        self.minmax_button.clicked.connect(self.toggle_minmax)
        minmax_bar = QHBoxLayout()
        minmax_bar.addStretch(1)
        minmax_bar.addWidget(self.minmax_button)
        layout.insertLayout(0, minmax_bar)
        self.save_edits_button = QPushButton("Save Edits (in viewer)")
        self.save_edits_button.setFixedWidth(260)
        self.save_edits_button.clicked.connect(self.save_edits)
        save_bar = QHBoxLayout()
        save_bar.addStretch(1)
        save_bar.addWidget(self.save_edits_button)
        layout.insertLayout(1, save_bar)
        # Set initial state to minimized (25%) and initialize toggle state
        screen = QApplication.primaryScreen().availableGeometry()
        w, h = int(screen.width()*0.25), int(screen.height()*0.25)
        self.resize(w, h)
        self.move((screen.width()-w)//2, (screen.height()-h)//2)
        self._is_custom_maximized = False
        self._has_been_shown = False
        self.edit_inserts = []  # Track all (insert_idx, moves) for this layer

    def move_extruder(self, direction):
        if not self.dpad_widget.isVisible():
            return
        if not self.moves:
            return
        idx = self.slider.value()
        dir_vectors = {
            "up":      np.array([-2.0, 0]),
            "down":    np.array([2.0, 0]),
            "left":    np.array([0, -2.0]),
            "right":   np.array([0, 2.0]),
            "up_right":   np.array([-2.0, 2.0]) / 1.414,
            "up_left":    np.array([-2.0, -2.0]) / 1.414,
            "down_right": np.array([2.0, 2.0]) / 1.414,
            "down_left":  np.array([2.0, -2.0]) / 1.414,
        }
        move_vec = dir_vectors[direction]
        session = self.edit_sessions[-1]
        # If moving back cancels last move, pop it
        if session['move_stack']:
            last_vec = session['move_stack'][-1]
            if np.allclose(move_vec, -last_vec):
                self.moves.pop(idx-1)
                self.current_index -= 1
                self.slider.setMaximum(len(self.moves))
                self.slider.setValue(idx-1)
                session['move_stack'].pop()
                session['current_idx'] = self.slider.value()-1
                if not session['move_stack']:
                    session['origin_idx'] = None
                    session['current_idx'] = None
                self.manual_origin_idx = session['origin_idx']
                self.manual_current_idx = session['current_idx']
                self.manual_move_stack = session['move_stack']
                self.update_plot()
                return
        # Otherwise, add new lifted travel move (sloped, no drop)
        last_move = self.moves[idx-1].copy()
        orig_x, orig_y, orig_z = last_move['x'], last_move['y'], last_move['z']
        dx, dy = move_vec[0], move_vec[1]
        lift_height = 1.5
        xy_dist = np.linalg.norm([dx, dy])
        slope_angle_rad = np.deg2rad(30)
        slope_dz = np.tan(slope_angle_rad) * xy_dist
        actual_lift = min(lift_height, slope_dz)
        # Move in XY and Z (sloped lift)
        lifted_move = last_move.copy()
        lifted_move['x'] += dx
        lifted_move['y'] += dy
        lifted_move['z'] = orig_z + actual_lift
        # Always set travel move type and do not extrude
        lifted_move['type'] = 'travel'
        lifted_move['e'] = last_move['e']  # No extrusion for travel
        self.moves.insert(idx, lifted_move)
        session['move_stack'].append(move_vec)
        session['current_idx'] = idx
        # Record the edit as (insert_idx, [move_dicts])
        insert_idx = self.slider.value() - 1 if self.slider.value() > 0 else 0
        # Map move index to G-code line index for precise insertion
        move_idx = self.slider.value() - 1 if self.slider.value() > 0 else 0
        gcode_line_idx = self.move_index_to_gcode_line(move_idx)
        moves_to_insert = [self.moves[move_idx]]
        # --- Multi-move edit support ---
        # If this is the first move in a new edit session, start a new edit_inserts entry
        if not self.edit_inserts or self.edit_inserts[-1][0] != self.move_index_to_gcode_line(idx-1):
            gcode_line_idx = self.move_index_to_gcode_line(idx-1)
            self.edit_inserts.append((gcode_line_idx, [lifted_move]))
        else:
            # Append to the last edit's move list
            self.edit_inserts[-1][1].append(lifted_move)
        self.manual_origin_idx = session['origin_idx']
        self.manual_current_idx = session['current_idx']
        self.manual_move_stack = session['move_stack']
        self.current_index += 1
        self.slider.setMaximum(len(self.moves))
        self.slider.setValue(idx+1)
        # If back at origin, reset indices and stack for this session
        origin = np.array([
            self.moves[session['origin_idx']]['x'],
            self.moves[session['origin_idx']]['y'],
            self.moves[session['origin_idx']]['z']
        ])
        current = np.array([
            lifted_move['x'], lifted_move['y'], lifted_move['z']
        ])
        if np.allclose(origin, current):
            session['origin_idx'] = None
            session['current_idx'] = None
            session['move_stack'] = []
            self.manual_origin_idx = None
            self.manual_current_idx = None
            self.manual_move_stack = []
        self.update_plot()

    def toggle_editor(self):
        if not self.dpad_widget.isVisible():
            self.dpad_widget.setVisible(True)
            self.editor_button.setText("Stop Editing")
            self.editor_button.setStyleSheet("background-color: red; color: white;")
            self.editor_active = True
            # Start a new edit session with a fixed color and its own origin
            idx = self.slider.value()-1
            # Assign color based on the number of sessions already created (fixed per session)
            color = self.session_colors[len(self.edit_sessions) % len(self.session_colors)]
            self.manual_origin_idx = idx
            self.manual_current_idx = idx
            self.manual_move_stack = []
            self.edit_sessions.append({
                'origin_idx': idx,
                'current_idx': idx,
                'color': color,
                'move_stack': [],
                'origin_coords': np.array([
                    self.moves[idx]['x'],
                    self.moves[idx]['y'],
                    self.moves[idx]['z']
                ])
            })
        else:
            self.dpad_widget.setVisible(False)
            self.editor_button.setText("Enable Toolpath Editor")
            self.editor_button.setStyleSheet("")
            self.editor_active = False
            #self.end_editing_and_patch_path()
        self.update_plot()

    def update_plot(self):
        self.gl_widget.clear()
        idx = self.slider.value()
        if not self.moves or idx < 2:
            self.status_label.setText("Not enough moves to display.")
            return
        pts = np.array([[m['x'], m['y'], m['z']] for m in self.moves[:idx]])
        # Add axes/grid for reference
        grid = gl.GLGridItem()
        grid.setSize(x=200, y=200)
        grid.setSpacing(x=10, y=10)
        self.gl_widget.addItem(grid)
        grid.translate((pts[:,0].min()+pts[:,0].max())/2, (pts[:,1].min()+pts[:,1].max())/2, 0)
        # Draw toolpath segments by type
        for i in range(1, idx):
            seg = np.array([pts[i-1], pts[i]])
            move_type = self.moves[i]['type']
            # Default: gray for unspecified
            color = (0.5,0.5,0.5,1)
            width = 3
            antialias = True
            if move_type == 'external_perimeter':
                color = (0.5,0,0.5,1)  # Purple
            elif move_type == 'perimeter':
                color = (0,0,1,1)  # Blue
            elif move_type == 'travel':
                color = (0,1,0,1)  # Green
                width = 2
                antialias = False
                # Dotted line: use many short segments
                dots = np.linspace(0, 1, 10)
                for j in range(0, len(dots)-1, 2):
                    dot_seg = np.vstack([
                        seg[0] + (seg[1] - seg[0]) * dots[j],
                        seg[0] + (seg[1] - seg[0]) * dots[j+1]
                    ])
                    dot_line = gl.GLLinePlotItem(pos=dot_seg, color=color, width=width, antialias=antialias, mode='lines')
                    dot_line.setGLOptions('translucent')
                    self.gl_widget.addItem(dot_line)
                continue  # Skip normal line for travel
            plt = gl.GLLinePlotItem(pos=seg, color=color, width=width, antialias=antialias, mode='lines')
            self.gl_widget.addItem(plt)
        # Draw all edit session net moves as colored lines (only if editor is active)
        if self.editor_active:
            for session in self.edit_sessions:
                # Only draw if session has a net move
                if session['origin_idx'] is not None and session['current_idx'] is not None:
                    # Only draw if both indices are within the current slider range
                    if session['origin_idx'] < len(self.moves) and session['current_idx'] < len(self.moves):
                        origin = session['origin_coords']
                        current = np.array([
                            self.moves[session['current_idx']]['x'],
                            self.moves[session['current_idx']]['y'],
                            self.moves[session['current_idx']]['z']
                        ])
                        if not np.allclose(origin, current):
                            seg = np.array([origin, current])
                            color = session['color']
                            line = gl.GLLinePlotItem(pos=seg, color=color, width=7, antialias=True, mode='lines')
                            self.gl_widget.addItem(line)
        # Draw extruder position: use sphere for first open, square for subsequent opens
        last = pts[idx-1]
        if self.extruder_head_style == 'sphere':
            try:
                md = gl.MeshData.sphere(rows=20, cols=20, radius=0.625)
                sphere = gl.GLMeshItem(meshdata=md, color=(1,0,0,1), smooth=True, shader='shaded', drawEdges=False)
                sphere.translate(last[0], last[1], last[2])
                sphere.setGLOptions('opaque')
                self.gl_widget.addItem(sphere)
            except Exception as e:
                scatter = gl.GLScatterPlotItem(pos=np.array([last]), color=(1,0,0,1), size=20, pxMode=True)
                scatter.setGLOptions('opaque')
                self.gl_widget.addItem(scatter)
        else:
            scatter = gl.GLScatterPlotItem(pos=np.array([last]), color=(1,0,0,1), size=20, pxMode=True)
            scatter.setGLOptions('opaque')
            self.gl_widget.addItem(scatter)
        self.status_label.setText(f"Showing {idx} moves / {len(self.moves)}")
        # Set camera to fit the data
        x_range = np.ptp(pts[:,0])
        y_range = np.ptp(pts[:,1])
        max_range = max(x_range, y_range, 100)
        center_coords = [(pts[:,0].min()+pts[:,0].max())/2, (pts[:,1].min()+pts[:,1].max())/2, (pts[:,2].min()+pts[:,2].max())/2]
        center = pg.Vector(center_coords[0], center_coords[1], center_coords[2])
        self.gl_widget.setCameraPosition(pos=center, distance=max_range, elevation=90, azimuth=0)
        self.gl_widget.setBackgroundColor('w')

    def add_slider_arrows(self, layout):
        arrow_back = QPushButton('◀')
        arrow_back.setFixedWidth(32)
        arrow_forward = QPushButton('▶')
        arrow_forward.setFixedWidth(32)
        arrow_back.clicked.connect(self.slider_back)
        arrow_forward.clicked.connect(self.slider_forward)
        layout.insertWidget(0, arrow_back)
        layout.addWidget(arrow_forward)
        self.arrow_back = arrow_back
        self.arrow_forward = arrow_forward

    def slider_back(self):
        val = self.slider.value()
        if val > self.slider.minimum():
            self.slider.setValue(val-1)

    def slider_forward(self):
        val = self.slider.value()
        if val < self.slider.maximum():
            self.slider.setValue(val+1)

    def set_layer(self, layer_lines, layer_idx=None, moves_override=None):
        self.layer_lines = layer_lines
        if layer_idx is not None:
            self.layer_idx = layer_idx
        elif not hasattr(self, 'layer_idx'):
            self.layer_idx = -1
        if moves_override is not None:
            self.moves = [dict(m) for m in moves_override]
        else:
            self.moves = self.parse_moves(layer_lines)
        self.current_index = len(self.moves) if self.moves else 0
        self.slider.setMaximum(len(self.moves) if self.moves else 1)
        self.slider.setValue(self.current_index)
        self.edit_sessions = []
        self.manual_origin_idx = None
        self.manual_current_idx = None
        self.manual_move_stack = []
        self.session_color_idx = 0
        self.update_plot()

    def parse_moves(self, lines):
        moves = []
        x = y = z = e = None
        last_x = last_y = last_z = last_e = None
        current_type = None
        for line in lines:
            line = line.strip()
            if not line or line.startswith('M'):
                continue
            if line.startswith(';TYPE:External perimeter'):
                current_type = 'external_perimeter'
                continue
            elif line.startswith(';TYPE:Perimeter'):
                current_type = 'perimeter'
                continue
            elif line.startswith(';TYPE:'):
                current_type = None
                continue
            if line.startswith('G0') or line.startswith('G1') or line.startswith('G01'):
                parts = line.split()
                for part in parts:
                    if part.startswith('X'):
                        x = float(part[1:])
                    elif part.startswith('Y'):
                        y = float(part[1:])
                    elif part.startswith('Z'):
                        z = float(part[1:])
                    elif part.startswith('E'):
                        try:
                            e = float(part[1:])
                        except ValueError:
                            pass
                is_travel = False
                if last_e is not None and (e is None or e == last_e):
                    is_travel = True
                if x is not None and y is not None:
                    moves.append({'x': x, 'y': y, 'z': z if z is not None else (last_z if last_z is not None else 0),
                                  'e': e if e is not None else (last_e if last_e is not None else 0),
                                  'type': 'travel' if is_travel else current_type})
                    last_x, last_y, last_z, last_e = x, y, z if z is not None else last_z, e if e is not None else last_e
            elif line.startswith('G2') or line.startswith('G3'):
                parts = line.split()
                for part in parts:
                    if part.startswith('X'):
                        x = float(part[1:])
                    elif part.startswith('Y'):
                        y = float(part[1:])
                    elif part.startswith('Z'):
                        z = float(part[1:])
                    elif part.startswith('E'):
                        try:
                            e = float(part[1:])
                        except ValueError:
                            pass
                is_travel = False
                if last_e is not None and (e is None or e == last_e):
                    is_travel = True
                if x is not None and y is not None:
                    moves.append({'x': x, 'y': y, 'z': z if z is not None else (last_z if last_z is not None else 0),
                                  'e': e if e is not None else (last_e if last_e is not None else 0),
                                  'type': 'travel' if is_travel else current_type})
                    last_x, last_y, last_z, last_e = x, y, z if z is not None else last_z, e if e is not None else last_e
        return moves

    def showEvent(self, event):
        # Always minimize to 25% the first time the dialog is shown and set state
        if not hasattr(self, '_has_been_shown') or not self._has_been_shown:
            screen = QApplication.primaryScreen().availableGeometry()
            w_min, h_min = int(screen.width()*0.25), int(screen.height()*0.25)
            self.resize(w_min, h_min)
            self.move((screen.width()-w_min)//2, (screen.height()-h_min)//2)
            self._is_custom_maximized = False
            self._has_been_shown = True
        super().showEvent(event)

    def toggle_minmax(self):
        screen = QApplication.primaryScreen().availableGeometry()
        w_min, h_min = int(screen.width()*0.25), int(screen.height()*0.25)
        w_max, h_max = int(screen.width()*0.95), int(screen.height()*0.95)
        cur_w, cur_h = self.width(), self.height()
        # Decide based on current size, not just state variable
        if abs(cur_w - w_min) < abs(cur_w - w_max):
            # Currently minimized, so maximize
            self.resize(w_max, h_max)
            self.move((screen.width()-w_max)//2, (screen.height()-h_max)//2)
            self._is_custom_maximized = True
        else:
            # Currently maximized or other, so minimize
            self.resize(w_min, h_min)
            self.move((screen.width()-w_min)//2, (screen.height()-h_min)//2)
            self._is_custom_maximized = False

    def closeEvent(self, event):
        # Hide instead of destroy, to persist OpenGL context
        self.hide()
        event.ignore()

    def save_edits(self):
        # Save all current edit insertions for this layer back to the main window
        if not hasattr(self, 'edit_inserts'):
            self.edit_inserts = []
        if self.mainwin and hasattr(self.mainwin, 'save_layer_edits'):
            self.mainwin.save_layer_edits(self.layer_idx, list(self.edit_inserts))
            QMessageBox.information(self, "Edits Saved", f"Edits for layer {self.layer_idx} saved.")
        else:
            QMessageBox.warning(self, "Warning", "Could not save edits: main window not found.")

    # Map a move index (from self.moves) to the corresponding G-code line index in self.layer_lines.
    def move_index_to_gcode_line(self, move_idx):
        move_count = 0
        for i, line in enumerate(self.layer_lines):
            line = line.strip()
            if not line or line.startswith('M'):
                continue
            if line.startswith('G0') or line.startswith('G1') or line.startswith('G01') or line.startswith('G2') or line.startswith('G3'):
                if move_count == move_idx:
                    return i
                move_count += 1
        return len(self.layer_lines)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GCodeEditor()
    window.show()
    sys.exit(app.exec_())