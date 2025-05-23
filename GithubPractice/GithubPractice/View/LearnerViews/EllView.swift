//
//  LumiView 2.swift
//  GithubPractice
//
//  Created by Ell Han on 5/23/25.
//


//
//  LumiView.swift
//  GithubPractice
//
//  Created by 정영진 on 5/22/25.
//

import SwiftUI

struct EllView: LearnerView {
    // TODO: 1. 이름, 팀 수정하고 커밋하기
    var name: String = "Ell"
    
    var team: String = "어떤팀?"
    
    var body: some View {
        Text("저의 이름은 \(name)입니다.")
            .font(.largeTitle)
        Text("저의 팀은 \(team) 입니다.")
            .font(.subheadline)
    }
}

#Preview {
    EllView()
}
