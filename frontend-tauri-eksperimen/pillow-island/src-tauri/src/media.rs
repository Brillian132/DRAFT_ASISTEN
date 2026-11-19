use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::Serialize;
use windows::Media::Control::{
    GlobalSystemMediaTransportControlsSession,
    GlobalSystemMediaTransportControlsSessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
};
use windows::Storage::Streams::DataReader;

#[derive(Serialize, Default)]
pub struct MediaInfo {
    pub active: bool,
    pub title: String,
    pub artist: String,
    pub playing: bool,
    pub position_ms: i64,
    pub duration_ms: i64,
}

fn current_session() -> windows::core::Result<Option<GlobalSystemMediaTransportControlsSession>> {
    let manager = GlobalSystemMediaTransportControlsSessionManager::RequestAsync()?.get()?;
    match manager.GetCurrentSession() {
        Ok(session) => Ok(Some(session)),
        Err(_) => Ok(None),
    }
}

pub fn get_info() -> windows::core::Result<MediaInfo> {
    let Some(session) = current_session()? else {
        return Ok(MediaInfo::default());
    };

    let props = session.TryGetMediaPropertiesAsync()?.get()?;
    let title = props.Title()?.to_string();
    let artist = props.Artist()?.to_string();

    let playing = session.GetPlaybackInfo()?.PlaybackStatus()? == Status::Playing;

    // satuan TimeSpan = 100 nanodetik, jadi dibagi 10.000 untuk milidetik
    let (position_ms, duration_ms) = match session.GetTimelineProperties() {
        Ok(tl) => {
            let start = tl.StartTime().map(|t| t.Duration).unwrap_or(0);
            let end = tl.EndTime().map(|t| t.Duration).unwrap_or(0);
            let pos = tl.Position().map(|t| t.Duration).unwrap_or(0);
            ((pos - start) / 10_000, (end - start) / 10_000)
        }
        Err(_) => (0, 0),
    };

    Ok(MediaInfo {
        active: !title.is_empty() || !artist.is_empty(),
        title,
        artist,
        playing,
        position_ms: position_ms.max(0),
        duration_ms: duration_ms.max(0),
    })
}

pub fn get_thumbnail() -> windows::core::Result<Option<String>> {
    let Some(session) = current_session()? else {
        return Ok(None);
    };

    let props = session.TryGetMediaPropertiesAsync()?.get()?;
    let thumb = match props.Thumbnail() {
        Ok(t) => t,
        Err(_) => return Ok(None),
    };

    let stream = thumb.OpenReadAsync()?.get()?;
    let size = stream.Size()? as u32;
    if size == 0 {
        return Ok(None);
    }

    let reader = DataReader::CreateDataReader(&stream)?;
    reader.LoadAsync(size)?.get()?;
    let mut buf = vec![0u8; size as usize];
    reader.ReadBytes(&mut buf)?;

    let mime = stream.ContentType()?.to_string();
    Ok(Some(format!("data:{};base64,{}", mime, STANDARD.encode(buf))))
}

pub fn control(action: &str) -> windows::core::Result<()> {
    if let Some(session) = current_session()? {
        match action {
            "play_pause" => {
                session.TryTogglePlayPauseAsync()?.get()?;
            }
            "next" => {
                session.TrySkipNextAsync()?.get()?;
            }
            "prev" => {
                session.TrySkipPreviousAsync()?.get()?;
            }
            _ => {}
        }
    }
    Ok(())
}