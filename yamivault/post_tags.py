"""Offline, deterministic post-text tags. Manual assignments remain independent."""
import html
import json
import re
import unicodedata
import uuid
import hashlib
import sqlite3
import time


def normalized(value):
    return unicodedata.normalize('NFKC', html.unescape(str(value))).replace('\ufe0e','').replace('\ufe0f','').casefold().strip()


def names(value):
    """Names/aliases are plain strings, never user-provided regular expressions."""
    from .manual_tags import normalize_tag
    parts = re.split(r'[,，、/／\n;；]+', value) if isinstance(value, str) else value
    result = []
    for part in parts:
        if str(part).strip():
            name = normalize_tag(str(part))
            if normalized(name) not in {normalized(n) for n in result}:result.append(name)
    if len(result) > 50:raise ValueError('別名は1タグにつき50個まで登録できます。')
    return result


def eligible(term):
    # Single-character colors/names are deliberately manual unless an actual
    # exact hashtag exists. English names use word boundaries below.
    return len(term) >= (3 if term.isascii() else 2)


def clean_body(text):
    body = normalized(text)
    body = re.sub(r'https?://\S+|www\.\S+', ' ', body)
    return re.sub(r'[#@][\w]+', ' ', body)


def extract_hashtags(text, supplied=()):
    text = re.sub(r'https?://\S+|www\.\S+', ' ', unicodedata.normalize('NFKC',html.unescape(str(text))),flags=re.I)
    result={}
    for name in [str(n).lstrip('#＃') for n in supplied if n] + re.findall(r'#(\w+)',text):
        result.setdefault(normalized(name),name)
    return list(result.values())


class Matcher:
    def __init__(self, definitions, rules, excluded):
        self.excluded = {normalized(n).lstrip('#') for n in excluded}
        self.exact = {};self.prefix = [];body_terms = {}
        for ident,name in definitions.items():
            rule = rules.get(ident,{})
            if rule.get('disabled') or (rule.get('created') and normalized(name) in self.excluded):continue
            for term in [name]+rule.get('aliases',[]):
                term = normalized(term)
                # Exact names have priority over aliases of another tag.
                if not rule.get('created'):self.exact[term]=ident
                else:self.exact.setdefault(term,ident)
                if eligible(term):
                    if rule.get('prefix',True):self.prefix.append((term,ident))
                    if rule.get('body',True):body_terms.setdefault(term,set()).add(ident)
        for ident,name in definitions.items():
            if not rules.get(ident,{}).get('disabled') and not rules.get(ident,{}).get('created'):
                self.exact[normalized(name)] = ident
        self.prefix.sort(key=lambda pair:(-len(pair[0]),pair[0],pair[1]))
        body_terms={term:{i for i in ids if not rules.get(i,{}).get('created') or self.exact.get(term)==i}
                    for term,ids in body_terms.items()}
        self.body_terms = body_terms
        # A trie avoids testing every registered name against every post and
        # also finds overlapping names at different positions in the body.
        self.trie={}
        for term,ids in body_terms.items():
            node=self.trie
            for char in term:node=node.setdefault(char,{})
            node[None]=(term.isascii(),ids)

    def hashtag_tag(self,name):
        key=normalized(name).lstrip('#')
        if key in self.excluded:return None
        if key in self.exact:return self.exact[key]
        return next((ident for term,ident in self.prefix if key.startswith(term)),None)

    def match(self,text,hashtags,*,body=True,hashes=True):
        result=set()
        if body and self.trie:
            body_text=clean_body(text)
            def word(char):return char.isascii() and (char.isalnum() or char=='_')
            for start,char in enumerate(body_text):
                node=self.trie.get(char)
                if node is None:continue
                end=start+1
                while node is not None:
                    terminal=node.get(None)
                    if terminal:
                        ascii_term,ids=terminal
                        if not ascii_term or ((start==0 or not word(body_text[start-1])) and (end==len(body_text) or not word(body_text[end]))):
                            result.update(ids)
                    if end==len(body_text):break
                    node=node.get(body_text[end]);end+=1
        if hashes:
            for name in extract_hashtags(text,hashtags):
                ident=self.hashtag_tag(name)
                if ident:result.add(ident)
        return result


class PostTagStoreMixin:
    def post_tag_options(self,library_id):
        template=self.get('post_tag_defaults',{})
        options=self.get('post_tag_options:'+library_id,template) if library_id else template
        legacy=bool(options) and 'min_posts' not in options
        return {'hashtags':options.get('hashtags',False),'body':options.get('body',False),
                'excluded':options.get('excluded',[]),
                'min_posts':options.get('min_posts',1 if legacy else 20),
                'max_tags':options.get('max_tags',0 if legacy else 50),
                'discover_hashtags':options.get('discover_hashtags',False),
                'keywords':options.get('keywords',[]),'tidy':options.get('tidy',False)}

    def post_tag_rules(self,library_id):
        return self.get('post_tag_rules:'+library_id,{})

    def _write_post_setting(self,key,value):
        self.db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                        (key,json.dumps(value,ensure_ascii=False)))

    def save_post_tag_options(self,library_id,hashtags=True,body=True,excluded=(),*,min_posts=None,max_tags=None,keywords=None,tidy=None,discover_hashtags=None):
        # Exclusions may contain far more than the per-tag alias limit.
        from .manual_tags import normalize_tag
        excluded=list(dict.fromkeys(normalize_tag(n) for n in excluded if str(n).strip()))
        options=self.post_tag_options(library_id)
        # Old callers retain their explicit "all hashtags" behavior.
        options.update(hashtags=bool(hashtags),body=bool(body),excluded=excluded,
                       min_posts=1 if min_posts is None else int(min_posts),
                       max_tags=0 if max_tags is None else int(max_tags))
        if options['min_posts']<1 or options['max_tags']<0:raise ValueError('使用回数は1以上、種類数は0以上で指定してください。')
        if keywords is not None:
            options['keywords']=[{'name':normalize_tag(k['name']),'aliases':names(k.get('aliases',[]))} for k in keywords]
        if tidy is not None:options['tidy']=bool(tidy)
        if discover_hashtags is not None:options['discover_hashtags']=bool(discover_hashtags)
        with self.db:self._write_post_setting('post_tag_options:'+library_id if library_id else 'post_tag_defaults',options)

    def initialize_post_tag_options(self,library_id):
        if self.get('post_tag_options:'+library_id) is None:
            with self.db:self._write_post_setting('post_tag_options:'+library_id,self.post_tag_options(library_id))

    def save_post_text(self,library_id,metadata):
        self.initialize_post_tag_options(library_id)
        rows=[]
        for pid,value in metadata.items():
            if not re.fullmatch(r'\d{1,30}',str(pid)) or not isinstance(value,dict):continue
            rows.append((library_id,str(pid),str(value.get('text',''))[:131072],
                         json.dumps(value.get('hashtags',[])[:500],ensure_ascii=False)))
        with self.db:self.db.executemany('''INSERT INTO post_text VALUES (?,?,?,?)
            ON CONFLICT(library_id,post_id) DO UPDATE SET text=excluded.text,hashtags_json=excluded.hashtags_json
            WHERE post_text.text IS NOT excluded.text OR post_text.hashtags_json IS NOT excluded.hashtags_json''',rows)
        return len(rows)

    def post_text_count(self,library_id):
        return self.db.execute('SELECT COUNT(*) FROM post_text WHERE library_id=?',(library_id,)).fetchone()[0]

    def reconcile_post_tags(self,library_id,assets,*,create_tags=True):
        """Reconcile one consistent WAL snapshot; retry concurrent writer upgrades.

        Cache keys include every input plus the exact derived rows. Color/group
        changes are intentionally absent: they cannot change tag assignments.
        """
        for attempt in range(3):
            try:
                with self.db:
                    self.db.execute('BEGIN')
                    return self._reconcile_post_tags(library_id,assets,create_tags=create_tags)
            except sqlite3.OperationalError as error:
                if getattr(error,'sqlite_errorcode',0) & 255 != sqlite3.SQLITE_BUSY or attempt==2:
                    raise
                time.sleep(.02*(attempt+1))

    def _reconcile_post_tags(self,library_id,assets,*,create_tags):
        options=self.post_tag_options(library_id);rules=self.post_tag_rules(library_id)
        definitions=dict(self.db.execute('SELECT tag_id,name FROM manual_tags WHERE library_id=?',(library_id,)))
        keyword_rules=[]
        configured={normalized(k['name']) for k in options['keywords']}
        for ident,rule in list(rules.items()):
            if rule.get('keyword') and not rule.get('disabled') and normalized(definitions.get(ident,'')) not in configured:
                rule=dict(rule,disabled=True);rules[ident]=rule;keyword_rules.append((ident,rule))
        for keyword in options['keywords']:
            ident=next((i for i,n in definitions.items() if normalized(n)==normalized(keyword['name'])),None)
            if ident is None and not create_tags:continue
            ident=ident or uuid.uuid4().hex
            definitions[ident]=keyword['name']
            old=rules.get(ident,{})
            aliases=keyword['aliases'] if old.get('keyword') else names(old.get('aliases',[])+keyword['aliases'])
            rule=dict(old,aliases=aliases,created=False,body=True,prefix=True,keyword=True,disabled=False)
            if rules.get(ident)!=rule:keyword_rules.append((ident,rule))
            rules[ident]=rule
        post_hashes={}
        for asset in assets:
            if asset.post_id:post_hashes.setdefault(asset.post_id,set()).add(asset.sha256)
        def records():
            for pid,text,tags in self.db.execute('SELECT post_id,text,hashtags_json FROM post_text WHERE library_id=? ORDER BY post_id',(library_id,)):
                if pid in post_hashes:yield pid,text,tags
        def digest_rows(rows):
            digest=hashlib.sha256()
            for row in rows:
                for value in row:
                    data=str(value).encode('utf-8');digest.update(len(data).to_bytes(8,'little'));digest.update(data)
            return digest.hexdigest()
        def input_digest():
            config={k:options[k] for k in ('hashtags','body','excluded','keywords','tidy','discover_hashtags','min_posts','max_tags')}
            digest=hashlib.sha256(json.dumps([config,definitions,rules,create_tags],sort_keys=True,ensure_ascii=False).encode('utf-8'))
            digest.update(digest_rows((pid,sha) for pid in sorted(post_hashes) for sha in sorted(post_hashes[pid])).encode())
            digest.update(digest_rows(records()).encode())
            for table in ('manual_asset_tags','post_tag_suppressions'):
                digest.update(digest_rows(self.db.execute(f'SELECT sha256,tag_id FROM {table} WHERE library_id=? ORDER BY sha256,tag_id',(library_id,))).encode())
            return digest.hexdigest()
        previous=set(self.db.execute('SELECT library_id,sha256,tag_id FROM post_asset_tags WHERE library_id=?',(library_id,)))
        output_digest=digest_rows(sorted(previous))
        signature=input_digest();cache_key='post_tag_cache_v2:'+library_id
        cached=self.get(cache_key,{})
        if not keyword_rules and cached.get('input')==signature and cached.get('output')==output_digest:
            return dict(cached['summary'],new_tags=0,new_links=0)
        for ident,rule in keyword_rules:
            name=definitions[ident]
            self.db.execute('INSERT OR IGNORE INTO manual_tags VALUES (?,?,?,?)',(library_id,ident,name,name.casefold()))
            self.db.execute('INSERT OR IGNORE INTO manual_tag_colors VALUES (?,?,?)',(library_id,ident,'teal'))
        if keyword_rules:self._write_post_setting('post_tag_rules:'+library_id,rules)
        discovered=[]
        if create_tags and options['hashtags'] and options['discover_hashtags']:
            # Count each hashtag once per artwork post, never per attachment.
            from collections import Counter
            counts=Counter();labels={};known=Matcher(definitions,rules,options['excluded'])
            excluded={normalized(n).lstrip('#') for n in options['excluded']}
            for pid,text,tags in records():
                for name in extract_hashtags(text,json.loads(tags)):
                    key=normalized(name)
                    if key in excluded or known.hashtag_tag(name):continue
                    counts[key]+=1;labels.setdefault(key,name)
            candidates=sorted((key for key,n in counts.items() if n>=options['min_posts']),
                              key=lambda key:(-counts[key],key))
            if options['max_tags']:
                retained=sum(bool(rules.get(i,{}).get('created')) for i in definitions)
                candidates=candidates[:max(0,options['max_tags']-retained)]
            from .manual_tags import normalize_tag
            for key in candidates:
                try:name=normalize_tag(labels[key])
                except ValueError:continue
                if any(normalized(n)==normalized(name) for n in definitions.values()):continue
                ident=uuid.uuid4().hex;definitions[ident]=name
                rules[ident]={'created':True,'body':False,'prefix':False,'discovered':True}
                self.db.execute('INSERT INTO manual_tags VALUES (?,?,?,?)',(library_id,ident,name,name.casefold()))
                self.db.execute('INSERT INTO manual_tag_colors VALUES (?,?,?)',(library_id,ident,'teal'))
                discovered.append(ident)
            if discovered:self._write_post_setting('post_tag_rules:'+library_id,rules)
        # Existing registry entries remain eligible after upgrades, including
        # legacy generated tags the user kept and any opt-in additions above.
        # Matcher still honors disabled rules and excluded legacy hashtags.
        active=definitions
        matcher=Matcher(active,rules,options['excluded'])
        assignments=set();posts=0
        for pid,text,tags in records():
            posts+=1
            if active and (options['body'] or options['hashtags']):
                matches=matcher.match(text,json.loads(tags),body=options['body'],hashes=options['hashtags'])
                assignments.update((library_id,sha,ident) for sha in post_hashes[pid] for ident in matches)
        assignments.update(row for row in previous if rules.get(row[2],{}).get('created'))
        self.db.executemany('DELETE FROM post_asset_tags WHERE library_id=? AND sha256=? AND tag_id=?',previous-assignments)
        self.db.executemany('INSERT OR IGNORE INTO post_asset_tags VALUES (?,?,?)',assignments-previous)
        if options['tidy']:
            groups,members=self.manual_tag_groups(library_id)
            used={i for (_l,_s,i) in assignments}
            manual={i for (i,) in self.db.execute('SELECT DISTINCT tag_id FROM manual_asset_tags WHERE library_id=?',(library_id,))}
            manual.update(i for (i,) in self.db.execute('SELECT DISTINCT tag_id FROM post_tag_suppressions WHERE library_id=?',(library_id,)))
            unused=[i for i in definitions if rules.get(i,{}).get('created') and i not in used|manual]
            if unused:
                for table in ('manual_tags','manual_tag_colors','post_tag_suppressions'):
                    self.db.executemany(f'DELETE FROM {table} WHERE library_id=? AND tag_id=?',[(library_id,i) for i in unused])
                for i in unused:rules.pop(i,None);members.pop(i,None);definitions.pop(i,None)
                self._write_tag_groups(library_id,groups,members)
                self._write_post_setting('post_tag_rules:'+library_id,rules)
                signature=input_digest()
        if discovered:signature=input_digest()
        effective=self.manual_tag_map(library_id)
        suppressed=set(self.db.execute('SELECT library_id,sha256,tag_id FROM post_tag_suppressions WHERE library_id=?',(library_id,)))
        summary={'posts':posts,'new_tags':len(discovered),'images':sum(bool(t) for t in effective.values()),
                 'automatic_links':len(assignments-suppressed),'new_links':len((assignments-previous)-suppressed)}
        self._write_post_setting(cache_key,{'input':signature,'output':digest_rows(sorted(assignments)),
                                          'summary':dict(summary,new_links=0,new_tags=0)})
        return summary

    def post_tag_removed(self,library_id,sha,ident,enabled):
        if enabled:self.db.execute('DELETE FROM post_tag_suppressions WHERE library_id=? AND sha256=? AND tag_id=?',(library_id,sha,ident))
        else:self.db.execute('INSERT OR IGNORE INTO post_tag_suppressions VALUES (?,?,?)',(library_id,sha,ident))
