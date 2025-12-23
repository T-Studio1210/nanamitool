#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
漢字データベースシードスクリプト
学年別漢字データをデータベースに投入します。
"""

import os
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import GradeKanji
from kanji_data import GRADE_KANJI_DATA, GRADE_NAMES

def seed_kanji():
    """漢字マスターデータをデータベースに投入"""
    with app.app_context():
        # テーブル作成（存在しない場合）
        db.create_all()
        
        # 既存データ数を確認
        existing_count = GradeKanji.query.count()
        if existing_count > 0:
            print(f'既に{existing_count}件の漢字データが存在します。')
            response = input('既存データを削除して再投入しますか？ (y/n): ')
            if response.lower() != 'y':
                print('処理をキャンセルしました。')
                return
            # 既存データ削除
            GradeKanji.query.delete()
            db.session.commit()
            print('既存データを削除しました。')
        
        total_added = 0
        
        for grade_code, kanji_list in GRADE_KANJI_DATA.items():
            grade_name = GRADE_NAMES.get(grade_code, grade_code)
            added_count = 0
            skipped_count = 0
            
            for kanji_char in kanji_list:
                # 重複チェック（同じ漢字が既に登録されていないか）
                existing = GradeKanji.query.filter_by(kanji=kanji_char).first()
                if existing:
                    skipped_count += 1
                    continue
                
                new_kanji = GradeKanji(
                    kanji=kanji_char,
                    grade=grade_code,
                )
                db.session.add(new_kanji)
                added_count += 1
            
            db.session.commit()
            total_added += added_count
            print(f'{grade_name}: {added_count}字追加（{skipped_count}字スキップ）')
        
        print(f'\n✅ 合計 {total_added} 字の漢字データを投入しました。')
        print(f'   データベース内の総漢字数: {GradeKanji.query.count()} 字')

if __name__ == '__main__':
    print('=' * 50)
    print('漢字マスターデータ投入スクリプト')
    print('=' * 50)
    seed_kanji()
