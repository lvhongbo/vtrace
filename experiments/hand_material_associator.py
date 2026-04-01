class HandMaterialAssociator:
    """
    单视角下的手-物-箱关联器
    解决：开箱后材料与QR码的关联问题
    """
    def __init__(self):
        self.active_hands = {}      # hand_id -> {pos, state: 'idle'|'grasp'|'hold'}
        self.active_boxes = {}      # box_id -> {qr, roi, state}
        self.material_lineage = {}  # material_id -> source_qr
        
        # 时序窗口（最近3秒的操作记忆）
        self.operation_memory = []
        
    def update(self, hands, boxes, materials, timestamp):
        """
        每帧更新关联关系
        """
        # 1. 更新手部状态（基于位置和姿态）
        for hand_id, hand_data in hands.items():
            # 检测抓取状态（手指闭合+移动）
            is_grasping = self._detect_grasp(hand_data)
            
            if is_grasping:
                # 查找手在哪个箱体内或附近
                nearest_box = self._find_nearest_box(hand_data['position'], boxes)
                if nearest_box:
                    hand_data['bound_box'] = nearest_box
        
        # 2. 新材料出现时，查找最近的手
        for mat_id, mat_data in materials.items():
            if mat_id not in self.material_lineage:
                # 新材料"出生"
                nearest_hand = self._find_nearest_hand(mat_data['position'], hands)
                if nearest_hand and 'bound_box' in nearest_hand:
                    # 继承QR码
                    box_id = nearest_hand['bound_box']
                    if box_id in self.active_boxes:
                        qr = self.active_boxes[box_id]['qr']
                        self.material_lineage[mat_id] = {
                            'qr': qr,
                            'birth_time': timestamp,
                            'birth_pos': mat_data['position']
                        }
                        logging.info(f"新材料{mat_id} 关联到箱子{box_id}(QR:{qr})")
        
        # 清理旧数据
        self._cleanup_old_data(timestamp)
    
    def get_material_qr(self, material_id):
        """查询材料的来源QR"""
        if material_id in self.material_lineage:
            return self.material_lineage[material_id]['qr']
        return None
    
    def _detect_grasp(self, hand_data):
        # 基于关键点检测手指闭合（实际使用MediaPipe Hands）
        return hand_data.get('is_closed', False)
    
    def _find_nearest_box(self, pos, boxes, threshold=100):
        """查找最近的手部所在的箱体"""
        min_dist = float('inf')
        nearest = None
        for box_id, box in boxes.items():
            dist = np.linalg.norm(np.array(pos) - np.array(box['center']))
            if dist < min_dist and dist < threshold:
                min_dist = dist
                nearest = box_id
        return nearest
    
    def _find_nearest_hand(self, pos, hands, threshold=80):
        """查找离材料最近的手"""
        min_dist = float('inf')
        nearest = None
        for hand_id, hand in hands.items():
            dist = np.linalg.norm(np.array(pos) - np.array(hand['position']))
            if dist < min_dist and dist < threshold:
                min_dist = dist
                nearest = hand
        return nearest