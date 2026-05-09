// app.jsx — main shell, navigation, tweaks, browser frame.

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "motion": "subtle",
  "density": "regular",
  "latin": "moderate",
  "readingMode": "paper",
  "meridian": true
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [section, setSection] = React.useState('splash');
  const [selectedUid, setSelectedUid] = React.useState('a1b2c3d4');
  const [cmdOpen, setCmdOpen] = React.useState(false);

  // ⌘K toggles cmd palette
  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setCmdOpen(o => !o); }
      if (e.key === 'Escape') setCmdOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const node = window.VAULT.find(n => n.uid === selectedUid);

  // route to active screen
  let screen;
  if (section === 'splash') {
    screen = <SplashScreen onEnter={() => setSection('all')} motion={t.motion}/>;
  } else if (section === 'all' || section.startsWith('t:')) {
    const filter = section.startsWith('t:') ? section.slice(2) : null;
    const filtered = filter ? window.VAULT.filter(n => n.type === filter) : window.VAULT;
    screen = (
      <div style={{flex:1, display:'flex', minWidth:0}}>
        <VaultIndex vault={filtered} selectedUid={selectedUid} onOpen={(uid)=>{setSelectedUid(uid); setSection('node');}}/>
      </div>
    );
  } else if (section === 'node') {
    screen = <NodeDetail node={node} vault={window.VAULT} onOpen={(uid)=>setSelectedUid(uid)} onBack={()=>setSection('all')} paper={t.readingMode === 'paper'}/>;
  } else if (section === 'compose') {
    screen = <Composer onBack={()=>setSection('all')} paper={t.readingMode === 'paper'}/>;
  } else if (section === 'empty') {
    screen = <EmptyState onCompose={()=>setSection('compose')}/>;
  } else if (section === 'settings') {
    screen = <SettingsScreen/>;
  } else if (section === 'graph') {
    // reuse the topology card from preview as iframe-like inline? simpler: link
    screen = <SettingsScreen/>; // fallback
  } else {
    screen = <VaultIndex vault={window.VAULT} selectedUid={selectedUid} onOpen={(uid)=>{setSelectedUid(uid); setSection('node');}}/>;
  }

  // density / motion / meridian flow into root attrs
  const flowDur = t.motion === 'static' ? '0s' : t.motion === 'ambient' ? '6s' : '3s';

  return (
    <div
      data-density={t.density}
      data-motion={t.motion}
      style={{
        height:'100%', width:'100%', display:'flex', minHeight:0,
        '--flow-dur': flowDur,
        '--bezel-dur': t.motion === 'ambient' ? '120s' : '240s',
        '--meridian-opacity': t.meridian ? (t.motion === 'ambient' ? 0.5 : 0.35) : 0,
      }}
    >
      {section !== 'splash' && (
        <VaultRail active={section} vault={window.VAULT} density={t.density}
          onNav={(id)=>{
            if (id === 'cmd') { setCmdOpen(true); return; }
            setSection(id);
          }}/>
      )}
      <div style={{flex:1, position:'relative', minWidth:0, display:'flex'}}>
        {screen}
        <CommandPalette open={cmdOpen} onClose={()=>setCmdOpen(false)} vault={window.VAULT}
          onOpen={(uid)=>{setSelectedUid(uid); setSection('node');}}/>
      </div>

      <TweaksPanel title="Topology Tweaks">
        <TweakSection label="Atmosphere"/>
        <TweakRadio label="Motion" value={t.motion}
          options={['static','subtle','ambient']}
          onChange={(v)=>setTweak('motion', v)}/>
        <TweakRadio label="Density" value={t.density}
          options={['sparse','regular','dense']}
          onChange={(v)=>setTweak('density', v)}/>
        <TweakRadio label="Latin" value={t.latin}
          options={['light','moderate','heavy']}
          onChange={(v)=>setTweak('latin', v)}/>
        <TweakToggle label="Meridian crosshairs" value={t.meridian}
          onChange={(v)=>setTweak('meridian', v)}/>
        <TweakSection label="Reading"/>
        <TweakRadio label="Reading mode" value={t.readingMode}
          options={['paper','dark']}
          onChange={(v)=>setTweak('readingMode', v)}/>
        <TweakSection label="Navigate"/>
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:6}}>
          {[
            ['splash','Splash'],['all','Vault'],['node','Node'],
            ['compose','Compose'],['empty','Empty'],['settings','Settings']
          ].map(([id,lbl])=>(
            <button key={id} onClick={()=>setSection(id)} style={{
              padding:'5px 8px',
              border:'0.5px solid rgba(0,0,0,0.1)', borderRadius:6,
              background: section === id ? 'rgba(0,0,0,0.78)' : 'rgba(255,255,255,0.6)',
              color: section === id ? '#fff' : 'inherit',
              fontFamily:'inherit', fontSize:11, fontWeight:500,
              cursor:'pointer'
            }}>{lbl}</button>
          ))}
        </div>
        <TweakButton label="Open ⌘K" onClick={()=>setCmdOpen(true)}/>
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
