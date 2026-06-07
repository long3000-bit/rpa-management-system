import logging
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Tuple

from app.storage.database import Database


class RpaTemplateService:
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_all_templates(self, template_type: str = "") -> Tuple[List[Dict], str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if template_type:
                cursor.execute('''
                    SELECT template_id, template_name, template_type, description,
                           import_field_mapping, field_mapping, workflow_steps,
                           success_rule, duplicate_rule, exe_config_id,
                           created_at, updated_at, enabled
                    FROM rpa_templates
                    WHERE template_type = ? AND enabled = 1
                    ORDER BY created_at DESC
                ''', (template_type,))
            else:
                cursor.execute('''
                    SELECT template_id, template_name, template_type, description,
                           import_field_mapping, field_mapping, workflow_steps,
                           success_rule, duplicate_rule, exe_config_id,
                           created_at, updated_at, enabled
                    FROM rpa_templates
                    WHERE enabled = 1
                    ORDER BY created_at DESC
                ''')
            
            rows = cursor.fetchall()
            templates = []
            
            for row in rows:
                template = dict(row)
                if template['import_field_mapping']:
                    try:
                        template['import_field_mapping'] = json.loads(template['import_field_mapping'])
                    except:
                        template['import_field_mapping'] = {}
                if template['field_mapping']:
                    try:
                        template['field_mapping'] = json.loads(template['field_mapping'])
                    except:
                        template['field_mapping'] = {}
                if template['workflow_steps']:
                    try:
                        template['workflow_steps'] = json.loads(template['workflow_steps'])
                    except:
                        template['workflow_steps'] = []
                templates.append(template)
            
            return templates, ""
            
        except Exception as e:
            logging.error(f"获取模板列表失败: {e}")
            return [], str(e)
    
    def get_template(self, template_id: str) -> Tuple[Dict, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT template_id, template_name, template_type, description,
                       import_field_mapping, field_mapping, workflow_steps,
                       success_rule, duplicate_rule, exe_config_id,
                       created_at, updated_at, enabled
                FROM rpa_templates
                WHERE template_id = ?
            ''', (template_id,))
            
            row = cursor.fetchone()
            if not row:
                return {}, "模板不存在"
            
            template = dict(row)
            if template['import_field_mapping']:
                try:
                    template['import_field_mapping'] = json.loads(template['import_field_mapping'])
                except:
                    template['import_field_mapping'] = {}
            if template['field_mapping']:
                try:
                    template['field_mapping'] = json.loads(template['field_mapping'])
                except:
                    template['field_mapping'] = {}
            if template['workflow_steps']:
                try:
                    template['workflow_steps'] = json.loads(template['workflow_steps'])
                except:
                    template['workflow_steps'] = []
            
            return template, ""
            
        except Exception as e:
            logging.error(f"获取模板失败: {e}")
            return {}, str(e)
    
    def save_template(self, template_data: Dict) -> Tuple[str, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            template_id = template_data.get('template_id', '')
            
            import_field_mapping = json.dumps(
                template_data.get('import_field_mapping', {}),
                ensure_ascii=False
            )
            field_mapping = json.dumps(
                template_data.get('field_mapping', {}),
                ensure_ascii=False
            )
            workflow_steps = json.dumps(
                template_data.get('workflow_steps', []),
                ensure_ascii=False
            )
            
            if template_id:
                cursor.execute('''
                    UPDATE rpa_templates
                    SET template_name = ?, template_type = ?, description = ?,
                        import_field_mapping = ?, field_mapping = ?, workflow_steps = ?,
                        success_rule = ?, duplicate_rule = ?, exe_config_id = ?,
                        updated_at = ?
                    WHERE template_id = ?
                ''', (
                    template_data['template_name'],
                    template_data['template_type'],
                    template_data.get('description', ''),
                    import_field_mapping,
                    field_mapping,
                    workflow_steps,
                    template_data.get('success_rule', ''),
                    template_data.get('duplicate_rule', ''),
                    template_data.get('exe_config_id', ''),
                    now,
                    template_id
                ))
            else:
                template_id = f"TPL{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
                
                cursor.execute('''
                    INSERT INTO rpa_templates
                    (template_id, template_name, template_type, description,
                     import_field_mapping, field_mapping, workflow_steps,
                     success_rule, duplicate_rule, exe_config_id,
                     created_at, updated_at, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ''', (
                    template_id,
                    template_data['template_name'],
                    template_data['template_type'],
                    template_data.get('description', ''),
                    import_field_mapping,
                    field_mapping,
                    workflow_steps,
                    template_data.get('success_rule', ''),
                    template_data.get('duplicate_rule', ''),
                    template_data.get('exe_config_id', ''),
                    now,
                    now
                ))
            
            conn.commit()
            
            logging.info(f"保存模板成功: {template_id}")
            
            return template_id, ""
            
        except Exception as e:
            conn.rollback()
            logging.error(f"保存模板失败: {e}")
            return "", str(e)
    
    def delete_template(self, template_id: str) -> Tuple[bool, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE rpa_templates SET enabled = 0 WHERE template_id = ?
            ''', (template_id,))
            
            conn.commit()
            
            return True, ""
            
        except Exception as e:
            conn.rollback()
            logging.error(f"删除模板失败: {e}")
            return False, str(e)
    
    def get_required_fields(self, template_id: str) -> Tuple[List[str], str]:
        template, error = self.get_template(template_id)
        if error:
            return [], error
        
        import_field_mapping = template.get('import_field_mapping', {})
        
        required_fields = []
        for field_name, mapping in import_field_mapping.items():
            if mapping.get('required', False):
                required_fields.append(field_name)
        
        return required_fields, ""